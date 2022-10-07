#================================================================================
#   CIE Colour Gamut Plotter - ICC to TRC
#     Copyright (C) 2022  Kampidh

#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.

#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.

#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <https://www.gnu.org/licenses/>.
#================================================================================

import struct
import warnings

import colour
import numpy as np
from numpy import vectorize

from numpy.linalg import inv
from scipy import interpolate

import concurrent.futures

class iccToTRC:
    def __init__(self, profile: bytes):
        self.prfByte = profile
        self.prfVer = self.extractICCversion()

        p_NameFull = self.extractDescription('desc')
        p_NameStrip = p_NameFull.replace('.icc', '').replace('.icm', '').strip()

        self.prfName = p_NameStrip

        self.prfType = ''
        self.prfPCS_white_check = True

        if self.validate():
            self.prfType = 'sdr'
            self.trcType = self.extractICCtag('rTRC')[0:4].decode('utf-8').strip()

            self.curveLen = int.from_bytes(self.extractICCtag('rTRC')[8:12], 'big')
            self.curveCont = self.extractICCtag('rTRC')[12:]

            self.paraParams = []
            self.paraMode = 0

            self.primaries = np.array([
                self.extractXYZdata('rXYZ'),
                self.extractXYZdata('gXYZ'),
                self.extractXYZdata('bXYZ')
            ])

            trcAddr = np.array([
                self.findTagPos('rTRC'),
                self.findTagPos('gTRC'),
                self.findTagPos('bTRC')
            ])

            trcEntries = np.array([
                self.extractICCtag('rTRC'),
                self.extractICCtag('gTRC'),
                self.extractICCtag('bTRC')
            ])

            if np.all(trcAddr == trcAddr[0]) or np.all(trcEntries == trcEntries[0]):
                self.uniformTRC = True
            else:
                self.uniformTRC = False

            self.trcTags = [
                'rTRC',
                'gTRC',
                'bTRC'
            ]

            self.trcTypes = [
                self.extractICCtag('rTRC')[0:4].decode('utf-8').strip(),
                self.extractICCtag('gTRC')[0:4].decode('utf-8').strip(),
                self.extractICCtag('bTRC')[0:4].decode('utf-8').strip()
            ]
            self.trcParaParams = [None] * 3
            self.trcCurvLens = [None] * 3
            self.trcCurvGammas = [None] * 3
            self.trcCurvLUTs = [None] * 3

            for x in range(3):
                if self.trcTypes[x] == 'para':
                    self.trcParaParams[x] = self.parametricParse(self.trcTags[x])
                    #
                    # experimental note 1: Speeds up conversion while sacrificing a bit of accuracy
                    # by converting the parametric function into curve LUT
                    # |
                    # v
                    self.trcCurvLUTs[x] = self.trcParaToCurv(self.trcParaParams[x])
                elif self.trcTypes[x] == 'curv':
                    self.trcCurvLens[x] = int.from_bytes(self.extractICCtag(self.trcTags[x])[8:12], 'big')
                    if self.trcCurvLens[x] == 1:
                        self.trcCurvGammas[x] = self.u8Fixed8NumberToFloat(self.extractICCtag(self.trcTags[x])[12:])
                    else:
                        self.trcCurvLUTs[x] = self.curvModeGetTable(self.trcTags[x])

            if self.trcType == 'para':
                self.paraMode = int.from_bytes(self.extractICCtag('rTRC')[8:10], 'big')
                self.paraParams = self.parametricParse('rTRC')

            if self.trcType == 'curv' and self.curveLen == 1:
                gamma = self.u8Fixed8NumberToFloat(self.curveCont)
                self.gamma = gamma
            else:
                gamma = 1.0
                self.gamma = gamma

            # vectorized function, unused if used with experimental note 1
            self.vTRCParaToLinearSingle = vectorize(self.trcParaToLinearSingle)


        elif self.findTagPos('A2B0') != -1:

            ##
            ## Workaround for HDR PQ Profile from PNG
            ## Especially the ITUR_2100_PQ_FULL profile from https://www.w3.org/TR/png-hdr-pq/
            ## Might be useful for other profiles that use A2B0 tags as well
            ##
            ## However, the matrix offsets and B curve will be useless because
            ## the end result of this module's calculation is a linear RGB, not XYZ
            ##

            self.trcType = 'A2B0'
            self.uniformTRC = False
            self.prfType = 'hdr'

            a2b0_buf = self.extractICCtag('A2B0')

            # should be multi-function A-to-B table type signature 'mAB'
            if a2b0_buf[0:4].decode('utf-8').strip() != 'mAB':
                raise Exception('A2B0 is used, but its not a multifunction "mAB" tag')
            
            a2b0_inCh = int(a2b0_buf[8])
            a2b0_outCh = int(a2b0_buf[9])

            # throw if not 3 channels
            if a2b0_inCh != 3 or a2b0_outCh != 3:
                raise Exception(f'Colour Channel mismatch, should be 3 but detected in:{a2b0_inCh} out:{a2b0_outCh}')
            
            a2b0_Bpos = int.from_bytes(a2b0_buf[12:16], 'big')
            a2b0_matpos = int.from_bytes(a2b0_buf[16:20], 'big')
            a2b0_Mpos = int.from_bytes(a2b0_buf[20:24], 'big')
            a2b0_LUTpos = int.from_bytes(a2b0_buf[24:28], 'big')
            a2b0_Apos = int.from_bytes(a2b0_buf[28:32], 'big')


            a2b0_tagsExist = np.array([a2b0_Bpos, a2b0_matpos, a2b0_Mpos, a2b0_LUTpos, a2b0_Apos]) != 0

            ## to be fixed, find a way to look for an absolute length rather than address to next tag
            ## so that if any of the tags are empty or overlapped, the code didn't break
            # a2b0_B = a2b0_buf[a2b0_Bpos:a2b0_matpos] if a2b0_tagsExist[0] else 0 # B curve never used here
            # a2b0_mat = a2b0_buf[a2b0_matpos:a2b0_Mpos] if a2b0_tagsExist[1] else 0
            # a2b0_M = a2b0_buf[a2b0_Mpos:a2b0_LUTpos] if a2b0_tagsExist[2] else 0
            # a2b0_LUT = a2b0_buf[a2b0_LUTpos:a2b0_Apos] if a2b0_tagsExist[3] else 0
            # a2b0_A = a2b0_buf[a2b0_Apos:] if a2b0_tagsExist[4] else 0

            ## or just remove the end position altogether ...
            ## as each parse functions will individually check the length of their own tags
            a2b0_B = a2b0_buf[a2b0_Bpos:] if a2b0_tagsExist[0] else 0 # B curve never used here
            a2b0_mat = a2b0_buf[a2b0_matpos:] if a2b0_tagsExist[1] else 0
            a2b0_M = a2b0_buf[a2b0_Mpos:] if a2b0_tagsExist[2] else 0
            a2b0_LUT = a2b0_buf[a2b0_LUTpos:] if a2b0_tagsExist[3] else 0
            a2b0_A = a2b0_buf[a2b0_Apos:] if a2b0_tagsExist[4] else 0

            #
            # Primaries from Matrix
            #
            if a2b0_tagsExist[1]:
                a2b0_Matrix = []
                for x in range(12):
                    ndx = x*4
                    a2b0_Matrix.append(self.s15Fixed16NumberToFloat(a2b0_mat[ndx:ndx+4]))

                self.primaries = np.array([
                    [a2b0_Matrix[0], a2b0_Matrix[3], a2b0_Matrix[6]],
                    [a2b0_Matrix[1], a2b0_Matrix[4], a2b0_Matrix[7]],
                    [a2b0_Matrix[2], a2b0_Matrix[5], a2b0_Matrix[8]]
                ])

                # Unused, however the matrix offset is still can be accessed if needed outside the module
                self.a2b0_MatrixOffset = np.array([
                    a2b0_Matrix[9],
                    a2b0_Matrix[10],
                    a2b0_Matrix[11]
                ])
            else:
                try:
                    self.primaries = np.array([
                    self.extractXYZdata('rXYZ'),
                    self.extractXYZdata('gXYZ'),
                    self.extractXYZdata('bXYZ')
                    ])
                except:
                    raise Exception('No primaries matrix found')

            #
            # A2B0 LUT
            #
            if a2b0_tagsExist[3]:
                a2b0_LUTdim = [
                    int(a2b0_LUT[0]),
                    int(a2b0_LUT[1]),
                    int(a2b0_LUT[2])
                ]

                a2b0_LUTlen = a2b0_LUTdim[0] * a2b0_LUTdim[1] * a2b0_LUTdim[2]
                a2b0_LUTdataType = int(a2b0_LUT[16])
                a2b0_LUTentries = a2b0_LUT[20:]

                a2b0_LUTbuf = []
                for x in range(a2b0_LUTlen):
                    if a2b0_LUTdataType == 1:
                        a2b0_LUTbuf.append(
                            [
                                int(a2b0_LUTentries[x*3])/255,
                                int(a2b0_LUTentries[(x*3)+1])/255,
                                int(a2b0_LUTentries[(x*3)+2])/255
                            ])
                    if a2b0_LUTdataType == 2:
                        a2b0_LUTbuf.append(
                            [
                                int.from_bytes(a2b0_LUTentries[(x*6):(x*6)+2], 'big')/65535,
                                int.from_bytes(a2b0_LUTentries[(x*6)+2:(x*6)+4], 'big')/65535,
                                int.from_bytes(a2b0_LUTentries[(x*6)+4:(x*6)+6], 'big')/65535,
                            ])

                a2b0_LUTarr = np.reshape(a2b0_LUTbuf, (a2b0_LUTdim[0],a2b0_LUTdim[1],a2b0_LUTdim[2],3))
                self.a2b0_LUTapp = colour.LUT3D(a2b0_LUTarr)
            else:
                # identity function
                lin_lut = np.array([[0, 0, 0], [0, 0, 1], [0, 1, 0], [0, 1, 1], [1, 0, 0], [1, 0, 1], [1, 1, 0], [1, 1, 1]], dtype=float)
                lin_lutrs = np.reshape(lin_lut, (2,2,2,3))
                self.a2b0_LUTapp = colour.LUT3D(lin_lutrs)

            #
            # M Curve
            #
            if a2b0_tagsExist[2]:
                if a2b0_M.find(b'para') != -1:
                    a2b0_Mcurv_ndx = []
                    a2b0_Mcurv_ndx.append(a2b0_M[0:].find(b'para'))
                    a2b0_Mcurv_ndx.append(a2b0_M.find(b'para', (a2b0_Mcurv_ndx[0] + 4)))
                    a2b0_Mcurv_ndx.append(a2b0_M.find(b'para', (a2b0_Mcurv_ndx[1] + 4)))

                    self.a2b0_Mtrc = [
                        self.trcParaToCurv(self.parametricParseSA(a2b0_M[a2b0_Mcurv_ndx[0]:a2b0_Mcurv_ndx[1]])),
                        self.trcParaToCurv(self.parametricParseSA(a2b0_M[a2b0_Mcurv_ndx[1]:a2b0_Mcurv_ndx[2]])),
                        self.trcParaToCurv(self.parametricParseSA(a2b0_M[a2b0_Mcurv_ndx[2]:]))
                    ]
                elif a2b0_M.find(b'curv') != -1:
                    a2b0_Mcurv_ndx = []
                    a2b0_Mcurv_ndx.append(a2b0_M[0:].find(b'para'))
                    a2b0_Mcurv_ndx.append(a2b0_M.find(b'para', (a2b0_Mcurv_ndx[0] + 4)))
                    a2b0_Mcurv_ndx.append(a2b0_M.find(b'para', (a2b0_Mcurv_ndx[1] + 4)))

                    self.a2b0_Mtrc = [
                        self.curvModeGetTableSA(a2b0_M[a2b0_Mcurv_ndx[0]:a2b0_Mcurv_ndx[1]]),
                        self.curvModeGetTableSA(a2b0_M[a2b0_Mcurv_ndx[1]:a2b0_Mcurv_ndx[2]]),
                        self.curvModeGetTableSA(a2b0_M[a2b0_Mcurv_ndx[2]:])
                    ]
            else:
                # identity function
                self.a2b0_Mtrc = [
                        np.array([[0, 1], [0, 1]], dtype='float'),
                        np.array([[0, 1], [0, 1]], dtype='float'),
                        np.array([[0, 1], [0, 1]], dtype='float')
                    ]

            #
            # A Curve
            #
            if a2b0_tagsExist[4]:
                if a2b0_A.find(b'curv') != -1:
                    a2b0_Acurv_ndx = []
                    a2b0_Acurv_ndx.append(a2b0_A[0:].find(b'curv'))
                    a2b0_Acurv_ndx.append(a2b0_A.find(b'curv', (a2b0_Acurv_ndx[0] + 4)))
                    a2b0_Acurv_ndx.append(a2b0_A.find(b'curv', (a2b0_Acurv_ndx[1] + 4)))

                    self.a2b0_Atrc = [
                        self.curvModeGetTableSA(a2b0_A[a2b0_Acurv_ndx[0]:a2b0_Acurv_ndx[1]]),
                        self.curvModeGetTableSA(a2b0_A[a2b0_Acurv_ndx[1]:a2b0_Acurv_ndx[2]]),
                        self.curvModeGetTableSA(a2b0_A[a2b0_Acurv_ndx[2]:])
                    ]
                elif a2b0_M.find(b'para') != -1:
                    a2b0_Acurv_ndx = []
                    a2b0_Acurv_ndx.append(a2b0_A[0:].find(b'curv'))
                    a2b0_Acurv_ndx.append(a2b0_A.find(b'curv', (a2b0_Acurv_ndx[0] + 4)))
                    a2b0_Acurv_ndx.append(a2b0_A.find(b'curv', (a2b0_Acurv_ndx[1] + 4)))

                    self.a2b0_Atrc = [
                        self.trcParaToCurv(self.parametricParseSA(a2b0_A[a2b0_Acurv_ndx[0]:a2b0_Acurv_ndx[1]])),
                        self.trcParaToCurv(self.parametricParseSA(a2b0_A[a2b0_Acurv_ndx[1]:a2b0_Acurv_ndx[2]])),
                        self.trcParaToCurv(self.parametricParseSA(a2b0_A[a2b0_Acurv_ndx[2]:]))
                    ]
            else:
                # identity function
                self.a2b0_Atrc = [
                    np.array([[0, 1], [0, 1]], dtype='float'),
                    np.array([[0, 1], [0, 1]], dtype='float'),
                    np.array([[0, 1], [0, 1]], dtype='float')
                ]

            #
            # Unused, but this also still can be accessed from outside the module if needed
            #
            # B Curve
            #
            if a2b0_tagsExist[0]:
                if a2b0_B.find(b'curv') != -1:
                    a2b0_Bcurv_ndx = []
                    a2b0_Bcurv_ndx.append(a2b0_B[0:].find(b'curv'))
                    a2b0_Bcurv_ndx.append(a2b0_B.find(b'curv', (a2b0_Bcurv_ndx[0] + 4)))
                    a2b0_Bcurv_ndx.append(a2b0_B.find(b'curv', (a2b0_Bcurv_ndx[1] + 4)))

                    self.a2b0_Btrc = [
                        self.curvModeGetTableSA(a2b0_B[a2b0_Bcurv_ndx[0]:a2b0_Bcurv_ndx[1]]),
                        self.curvModeGetTableSA(a2b0_B[a2b0_Bcurv_ndx[1]:a2b0_Bcurv_ndx[2]]),
                        self.curvModeGetTableSA(a2b0_B[a2b0_Bcurv_ndx[2]:])
                    ]
                elif a2b0_M.find(b'para') != -1:
                    a2b0_Bcurv_ndx = []
                    a2b0_Bcurv_ndx.append(a2b0_B[0:].find(b'curv'))
                    a2b0_Bcurv_ndx.append(a2b0_B.find(b'curv', (a2b0_Bcurv_ndx[0] + 4)))
                    a2b0_Bcurv_ndx.append(a2b0_B.find(b'curv', (a2b0_Bcurv_ndx[1] + 4)))

                    self.a2b0_Btrc = [
                        self.trcParaToCurv(self.parametricParseSA(a2b0_B[a2b0_Bcurv_ndx[0]:a2b0_Bcurv_ndx[1]])),
                        self.trcParaToCurv(self.parametricParseSA(a2b0_B[a2b0_Bcurv_ndx[1]:a2b0_Bcurv_ndx[2]])),
                        self.trcParaToCurv(self.parametricParseSA(a2b0_B[a2b0_Bcurv_ndx[2]:]))
                    ]
            else:
                # identity function
                self.a2b0_Btrc = [
                    np.array([[0, 1], [0, 1]], dtype='float'),
                    np.array([[0, 1], [0, 1]], dtype='float'),
                    np.array([[0, 1], [0, 1]], dtype='float')
                ]

            if np.all(self.a2b0_Mtrc == self.a2b0_Mtrc[0]) and np.all(self.a2b0_Atrc == self.a2b0_Atrc[0]):
                self.uniformTRC = True
            else:
                self.uniformTRC = False
        else:
            raise Exception('Profile not supported')


    def trcDecode(self, input):
        if self.prfType == 'sdr':
            if self.uniformTRC:
                result = self.trcDecodeToLinearSingle(input)
                # result = self.trcDecodeToLinear_MP(input) # debug
            else:
                result = self.trcDecodeToLinear_MP(input)
            return result
        elif self.prfType == 'hdr':
            if self.uniformTRC:
                result = self.trcDecodeA2B0Single(input)
                # result = self.trcDecodeA2B0_MP(input) # debug
            else:
                result = self.trcDecodeA2B0_MP(input)
            return result

    def trcDecodeToLinear_MP(self, input):
        inRGB = [input[...,0], input[...,1], input[...,2]]
        bufRGB = [None] * 3

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for x in range(3):
                if self.trcTypes[x] == 'curv':
                    bufRGB[x] = executor.submit(self.curveToLinearNP_Single, inRGB[x], x)
                elif self.trcTypes[x] == 'para':
                    # bufRGB[x] = executor.submit(self.vTRCParaToLinearSingle, inRGB[x], *self.trcParaParams[x])
                    bufRGB[x] = executor.submit(self.paraCurveToLinearNP_Single, inRGB[x], x) # experimental note 1
                else:
                    raise Exception(f'TRC type {self.trcTypes[x]} is not supported')

        r = bufRGB[0].result()
        g = bufRGB[1].result()
        b = bufRGB[2].result()
        rgb = np.stack((r, g, b), axis=-1)
        # result = rgb

        return rgb

    #
    # Deprecated, only use when Multiprocess didn't work
    #
    def trcDecodeToLinear_SP(self, input):
        inRGB = [input[...,0], input[...,1], input[...,2]]
        bufRGB = [None] * 3

        for x in range(3):
            if self.trcTypes[x] == 'curv':
                bufRGB[x] = self.curveToLinearNP_Single(inRGB[x], x)
            elif self.trcTypes[x] == 'para':
                # bufRGB[x] = self.vTRCParaToLinearSingle(inRGB[x], *self.trcParaParams[x])
                bufRGB[x] = self.paraCurveToLinearNP_Single(inRGB[x], x) # experimental note 1
        
        r = bufRGB[0]
        g = bufRGB[1]
        b = bufRGB[2]
        rgb = np.stack((r, g, b), axis=-1)
        # result = rgb

        return rgb

    def trcDecodeToLinearSingle(self, input):
        if self.trcTypes[0] == 'curv':
            result = self.curveToLinearNP_Single(input, 0)
        elif self.trcTypes[0] == 'para':
            # result = self.vTRCParaToLinearSingle(input, *self.trcParaParams[0])
            result = self.paraCurveToLinearNP_Single(input, 0) # experimental note 1
        else:
            raise Exception(f'TRC type {self.trcTypes[0]} is not supported')
        return result

    def curveToLinearNP_Single(self, input: float, channel: int) -> float:
        if self.trcCurvLens[channel] == 1:
            calc = input ** self.trcCurvGammas[channel]
            return calc
        else:
            # use scipy interpolate to extrapolate values over 1.0 (HDR)
            f = interpolate.interp1d(self.trcCurvLUTs[channel][0], self.trcCurvLUTs[channel][1], fill_value='extrapolate')
            return f(input)

            # numpy version
            # return np.interp(input, self.trcCurvLUTs[channel][0], self.trcCurvLUTs[channel][1])

    def trcDecodeA2B0Single(self, input):
        x = self.paraCurveToLinearNP_SingleSA(input, self.a2b0_Atrc, 0)
        y = self.a2b0_LUTapp.apply(x)
        result = self.paraCurveToLinearNP_SingleSA(y, self.a2b0_Mtrc, 0)
        return result

    def trcDecodeA2B0_MP(self, input):
        inRGB = [input[...,0], input[...,1], input[...,2]]
        bufRGB = [None] * 3

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for x in range(3):
                bufRGB[x] = executor.submit(self.paraCurveToLinearNP_SingleSA, inRGB[x], self.a2b0_Atrc, x)

        rA = bufRGB[0].result()
        gA = bufRGB[1].result()
        bA = bufRGB[2].result()
        rgbA = np.stack((rA, gA, bA), axis=-1)

        B = self.a2b0_LUTapp.apply(rgbA)

        RGB_A = [B[...,0], B[...,1], B[...,2]]
        bufRGB_A = [None] * 3

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for x in range(3):
                bufRGB_A[x] = executor.submit(self.paraCurveToLinearNP_SingleSA, RGB_A[x], self.a2b0_Mtrc, x)

        rB = bufRGB_A[0].result()
        gB = bufRGB_A[1].result()
        bB = bufRGB_A[2].result()
        rgbB = np.stack((rB, gB, bB), axis=-1)

        # result = rgbB
        
        return rgbB

    #
    # experimental note 1
    #
    def paraCurveToLinearNP_Single(self, input: float, channel: int) -> float:

        # use scipy interpolate to extrapolate values over 1.0 (HDR)
        f = interpolate.interp1d(self.trcCurvLUTs[channel][0], self.trcCurvLUTs[channel][1], fill_value='extrapolate')
        return f(input)

        # numpy version
        # return np.interp(input, self.trcCurvLUTs[channel][0], self.trcCurvLUTs[channel][1])

    #
    # Standalone
    #
    def paraCurveToLinearNP_SingleSA(self, input: float, trc, channel: int) -> float:

        # use scipy interpolate to extrapolate values over 1.0 (HDR)
        f = interpolate.interp1d(trc[channel][0], trc[channel][1], fill_value='extrapolate')
        return f(input)

    def trcParaToLinearSingle(self, x: float, *args) -> float:
        if len(args) == 1:
            Y = pow(x, args[0])
            return Y

        elif len(args) == 3:
            if x >= (-args[2] / args[1]):
                Y = pow(((args[1] * x) + args[2]), args[0])
            elif x < (-args[2] / args[1]):
                Y = 0
            return Y

        elif len(args) == 4:
            if x >= (-args[2] / args[1]):
                Y = pow(((args[1] * x) + args[2]), args[0]) + args[3]
            elif x < (-args[2] / args[1]):
                Y = args[3]
            return Y

        elif len(args) == 5:
            if x >= args[4]:
                Y = pow(((args[1] * x) + args[2]), args[0])
            elif x < args[4]:
                Y = (args[3] * x)
            return Y

        elif len(args) == 7:
            if x >= args[4]:
                Y = pow(((args[1] * x) + args[2]), args[0]) + args[5]
            elif x < args[4]:
                Y = ((args[3] * x) + args[6])
            return Y

        else:
            return 0
    #
    # experimental note 1
    #
    def trcParaToCurv(self, *args):
        LUTndx = []
        LUTlist = []

        # increase LUT length to increase accuracy
        LUTlen = 8192

        args = np.array(args, dtype=float)[0]

        for xI in range(LUTlen):
            x = xI / (LUTlen - 1)

            if len(args) == 1:
                Y = pow(x, args[0])

            elif len(args) == 3:
                if x >= (-args[2] / args[1]):
                    Y = pow(((args[1] * x) + args[2]), args[0])
                elif x < (-args[2] / args[1]):
                    Y = 0

            elif len(args) == 4:
                if x >= (-args[2] / args[1]):
                    Y = pow(((args[1] * x) + args[2]), args[0]) + args[3]
                elif x < (-args[2] / args[1]):
                    Y = args[3]

            elif len(args) == 5:
                if x >= args[4]:
                    Y = pow(((args[1] * x) + args[2]), args[0])
                elif x < args[4]:
                    Y = (args[3] * x)

            elif len(args) == 7:
                if x >= args[4]:
                    Y = pow(((args[1] * x) + args[2]), args[0]) + args[5]
                elif x < args[4]:
                    Y = ((args[3] * x) + args[6])

            LUTndx.append(x)
            LUTlist.append(Y)

        tb = np.array([LUTndx, LUTlist], dtype=float)

        return tb

    def curvModeGetTable(self, tag: str):

        curveLen = int.from_bytes(self.extractICCtag(tag)[8:12], 'big')
        curveCont = self.extractICCtag(tag)[12:]

        if curveLen == 1:
            return False

        LUTndx = []
        LUTlist = []

        for x in range(curveLen*2):
            if x % 2 != 0:
                continue
            ndx = int(x/2)
            LUTndx.append(ndx)
            LUTlist.append(int.from_bytes(curveCont[x:x+2], 'big'))

        LUTndxN = np.array(LUTndx)
        LUTlistN = np.array(LUTlist)

        xMax = np.max(LUTndxN)
        yMax = np.max(LUTlistN)

        xNorm = np.array(LUTndxN / xMax)
        yNorm = np.array(LUTlistN / yMax)

        tb = np.array([xNorm, yNorm])
        return tb

    #
    # Standalone
    #
    def curvModeGetTableSA(self, byteIn):

        curveLen = int.from_bytes(byteIn[8:12], 'big')
        curveCont = byteIn[12:]

        if curveLen == 1:
            return False
        if curveLen == 0:
            # Identity function
            return np.array([[0, 1], [0, 1]], dtype='float')

        LUTndx = []
        LUTlist = []

        for x in range(curveLen*2):
            if x % 2 != 0:
                continue
            ndx = int(x/2)
            LUTndx.append(ndx)
            LUTlist.append(int.from_bytes(curveCont[x:x+2], 'big'))

        LUTndxN = np.array(LUTndx)
        LUTlistN = np.array(LUTlist)

        xMax = np.max(LUTndxN)
        yMax = np.max(LUTlistN)

        xNorm = np.array(LUTndxN / xMax)
        yNorm = np.array(LUTlistN / yMax)

        tb = np.array([xNorm, yNorm])
        return tb

    def parametricParse(self, tag: str) -> list:
        paraParams = []

        if self.trcType == 'para':
            paraMode = int.from_bytes(self.extractICCtag(tag)[8:10], 'big')
            if paraMode == 0:
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[12:16]))
            elif paraMode == 1:
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[12:16]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[16:20]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[20:24]))
            elif paraMode == 2:
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[12:16]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[16:20]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[20:24]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[24:28]))
            elif paraMode == 3:
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[12:16]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[16:20]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[20:24]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[24:28]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[28:32]))
            elif paraMode == 4:
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[12:16]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[16:20]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[20:24]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[24:28]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[28:32]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[32:36]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(tag)[36:40]))
        else:
            paraMode = 0
        
        return paraParams

    #
    # Standalone
    #
    def parametricParseSA(self, byteIn) -> list:
        paraParams = []

        paraMode = int.from_bytes(byteIn[8:10], 'big')
        if paraMode == 0:
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[12:16]))
        elif paraMode == 1:
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[12:16]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[16:20]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[20:24]))
        elif paraMode == 2:
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[12:16]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[16:20]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[20:24]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[24:28]))
        elif paraMode == 3:
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[12:16]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[16:20]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[20:24]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[24:28]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[28:32]))
        elif paraMode == 4:
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[12:16]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[16:20]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[20:24]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[24:28]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[28:32]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[32:36]))
            paraParams.append(self.s15Fixed16NumberToFloat(byteIn[36:40]))
        
        return paraParams
        
    def profileFromEmbed(self, pName = '') -> colour.RGB_Colourspace:

        pRedPrimary = colour.XYZ_to_xy(self.primaries[0])
        pGreenPrimary = colour.XYZ_to_xy(self.primaries[1])
        pBluePrimary = colour.XYZ_to_xy(self.primaries[2])

        wt_pcs = np.array([0.34570292, 0.35853753])
        wt_d65 = np.array([0.31270049, 0.32900094])

        wt_pcs_D50_byte = b'\x00\x00\xF6\xD6\x00\x01\x00\x00\x00\x00\xD3\x2D'
        wt_pcs_profile_byte = self.prfByte[68:80]

        if not wt_pcs_D50_byte == wt_pcs_profile_byte:
            warnings.warn("Embedded profile PCS illuminant is not D50")
            self.prfPCS_white_check = False
        else:
            self.prfPCS_white_check = True

        if self.extractICCtag('chad') != -1:
            chAD_mtx = self.extractSF32data('chad')
            chad_exist = True
        else:
            chad_exist = False

        pcsWhite_XYZ = self.extractXYZPCS()
        wt_pcs = colour.XYZ_to_xy(pcsWhite_XYZ)
        pWhite_XYZ = self.extractXYZdata('wtpt')

        sinMTX = np.array([[1,0,0],[0,1,0],[0,0,1]], dtype=float)

        if chad_exist and not np.all(chAD_mtx == sinMTX):
            # use chromatic_adaptation tag if the profile has it
            # ignore if chromatic adaptation matrix is identity
            pCAinv = inv(chAD_mtx)
            pWhiteCA = np.dot(pCAinv, pcsWhite_XYZ)
            pWhitexy = colour.XYZ_to_xy(pWhiteCA)
            wt_prf = pWhitexy
        else:
            # else, take from the media_white_point tag
            wt_prf = colour.XYZ_to_xy(pWhite_XYZ)

        if pName:
            p_Name = pName
        else:
            p_Name = self.prfName

        pRGBD50 = np.array([pRedPrimary[0], pRedPrimary[1], pGreenPrimary[0], pGreenPrimary[1], pBluePrimary[0], pBluePrimary[1]])

        try:
            pRGBD65 = colour.chromatically_adapted_primaries(pRGBD50, wt_pcs, wt_prf, 'Bradford')
        except:
            pRGBD65 = pRGBD50

        try:
            colourspace = colour.RGB_Colourspace(p_Name, pRGBD65, wt_prf)
        except:
            colourspace = ''

        return colourspace

    def u8Fixed8NumberToFloat(self, u: bytes) -> float:
        t = struct.unpack('>H', u)
        g = (2**-8) * t[0]
        return g

    def s15Fixed16NumberToFloat(self, s: bytes) -> float:
        t = struct.unpack('>l', s)
        g = (2**-16) * t[0]
        return g

    def u16Fixed16NumberToFloat(self, s: bytes) -> float:
        t = struct.unpack('>L', s)
        g = (2**-16) * t[0]
        return g

    def extractSF32data(self, sf32Tag):

        tagBuffer = self.extractICCtag(sf32Tag)
        tagType = tagBuffer[0:4].decode().strip()

        if tagType != 'sf32':
            raise Exception('Selected tag is not sf32')
            # return 0

        sf32arr = np.array(
            [
                [
                    self.s15Fixed16NumberToFloat(tagBuffer[8:12]),
                    self.s15Fixed16NumberToFloat(tagBuffer[12:16]),
                    self.s15Fixed16NumberToFloat(tagBuffer[16:20])
                ],
                [
                    self.s15Fixed16NumberToFloat(tagBuffer[20:24]),
                    self.s15Fixed16NumberToFloat(tagBuffer[24:28]),
                    self.s15Fixed16NumberToFloat(tagBuffer[28:32])
                ],
                [
                    self.s15Fixed16NumberToFloat(tagBuffer[32:36]),
                    self.s15Fixed16NumberToFloat(tagBuffer[36:40]),
                    self.s15Fixed16NumberToFloat(tagBuffer[40:44])
                ],
            ])

        return sf32arr

    def extractXYZPCS(self):

        arrXYZ = np.array([
            self.s15Fixed16NumberToFloat(self.prfByte[68:72]),
            self.s15Fixed16NumberToFloat(self.prfByte[72:76]),
            self.s15Fixed16NumberToFloat(self.prfByte[76:80])
        ])

        return arrXYZ

    def extractXYZdata(self, xyzTag):

        tagBuffer = self.extractICCtag(xyzTag)
        tagType = tagBuffer[0:4].decode().strip()

        if tagType != 'XYZ':
            raise Exception('Selected tag is not XYZ')
            # return 0

        arrXYZ = np.array([
            self.s15Fixed16NumberToFloat(tagBuffer[8:12]),
            self.s15Fixed16NumberToFloat(tagBuffer[12:16]),
            self.s15Fixed16NumberToFloat(tagBuffer[16:20])
        ])

        return arrXYZ

    def extractICCtag(self, byteToFind) -> bytes:

        # only search in tag fields after the header
        tagCount = int.from_bytes(self.prfByte[128:132], 'big')
        tagCountLen = tagCount * 12
        tagBuffer = self.prfByte[132:132+tagCountLen]

        tagNdx = tagBuffer.find(byteToFind.encode('utf-8'))

        # terminate if no tag is found
        if tagNdx == -1:
            # raise Exception('Cannot find selected tag in tags list')
            return -1

        tagPosNdx = int.from_bytes(tagBuffer[tagNdx+4:tagNdx+8], 'big')
        tagLen = int.from_bytes(tagBuffer[tagNdx+8:tagNdx+12], 'big')

        # Deprecated
        # tagNdx = self.prfByte.find(byteToFind.encode('utf-8'))
        # tagPosNdx = int.from_bytes(self.prfByte[tagNdx+4:tagNdx+8], 'big')
        # tagLen = int.from_bytes(self.prfByte[tagNdx+8:tagNdx+12], 'big')

        tagContent = self.prfByte[tagPosNdx:tagPosNdx+tagLen]

        return tagContent

    def findTagPos(self, byteToFind) -> int:

        # only search in tag fields after the header
        tagCount = int.from_bytes(self.prfByte[128:132], 'big')
        tagCountLen = tagCount * 12
        tagBuffer = self.prfByte[132:132+tagCountLen]

        tagNdx = tagBuffer.find(byteToFind.encode('utf-8'))

        # terminate if no tag is found
        if tagNdx == -1:
            # raise  Exception('Cannot find selected tag in tags list')
            return -1

        tagPosNdx = int.from_bytes(tagBuffer[tagNdx+4:tagNdx+8], 'big')

        return tagPosNdx

    def extractDescription(self, descTag = 'desc') -> str:

        tagBuffer = self.extractICCtag(descTag)
        tagType = tagBuffer[0:4].decode().strip()

        if tagType == 'desc':
            firstNdx = 12
            lastNdx = tagBuffer[firstNdx:].find(b'\x00') + firstNdx
            descStr = tagBuffer[firstNdx:lastNdx].decode('utf-8').replace('\x00','').strip()

            return descStr

        elif tagType == 'mluc':
            strLen = int.from_bytes(tagBuffer[20:24], 'big')
            strfirstNdx = int.from_bytes(tagBuffer[24:28], 'big')
            descStr = tagBuffer[strfirstNdx:strfirstNdx+strLen].decode('utf-8').replace('\x00','').strip()

            return descStr

        else:
            return 'Profile description not found'

    def extractICCversion(self) -> float:

        tagverHi = int.from_bytes(self.prfByte[8:9], 'big')
        tagverLo = int.from_bytes(self.prfByte[9:10], 'big')
        tagverLoNH = tagverLo >> 4
        tagverLoNL = tagverLo & 0x0F

        tagversionICC = float(f'{tagverHi}.{tagverLoNH}{tagverLoNL}')
        return tagversionICC

    def extractColorSpace(self) -> str:
        strSpace = self.prfByte[16:20].decode('utf-8').strip()
        return strSpace

    def validate(self):
        headerTag = self.prfByte[36:40].decode('utf-8').strip()
        
        if headerTag != 'acsp':
            raise Exception(f'Identifier "{headerTag}" is not a valid ICC profile.')
            # return False

        PCStag = self.prfByte[20:24].decode('utf-8').strip()
        if PCStag != 'XYZ':
            raise Exception(f'PCS is {PCStag}, only XYZ is allowed')

        testEntries = np.array([
            self.findTagPos('rXYZ'),
            self.findTagPos('gXYZ'),
            self.findTagPos('bXYZ'),
            self.findTagPos('rTRC'),
            self.findTagPos('gTRC'),
            self.findTagPos('bTRC'),
            self.findTagPos('wtpt')
        ])

        if np.any(testEntries == -1):
            return False
        else:
            return True
