import struct
from PIL import ImageCms

import colour
import numpy as np
from numpy import vectorize

from numpy.linalg import inv
import matplotlib.pyplot as plt

class iccToTRC:
    def __init__(self, profile: ImageCms.ImageCmsProfile):
        self.prf = profile
        self.prfByte = profile.tobytes()
        self.prfVer = profile.profile.version

        ps_Name = ImageCms.getProfileDescription(self.prf)
        p_Name = ps_Name.replace('.icc', '').replace('.icm', '').strip()

        self.prfName = p_Name

        self.trcType = self.extractICCtag(self.prf, b'rTRC')[0:4].decode('utf-8').strip()

        self.curveLen = int.from_bytes(self.extractICCtag(self.prf, b'rTRC')[8:12], 'big')
        self.curveCont = self.extractICCtag(self.prf, b'rTRC')[12:]

        self.paraParams = []
        self.paraMode = 0

        if self.trcType == 'para':
            self.paraMode = int.from_bytes(self.extractICCtag(self.prf, b'rTRC')[8:10], 'big')
            self.paraParams = self.parametricParse('rTRC')

            self.rParaMode = int.from_bytes(self.extractICCtag(self.prf, b'rTRC')[8:10], 'big')
            self.rParaParams = self.parametricParse('rTRC')
            self.gParaMode = int.from_bytes(self.extractICCtag(self.prf, b'rTRC')[8:10], 'big')
            self.gParaParams = self.parametricParse('gTRC')
            self.bParaMode = int.from_bytes(self.extractICCtag(self.prf, b'bTRC')[8:10], 'big')
            self.bParaParams = self.parametricParse('bTRC')
            
        if self.trcType == 'curv' and not self.curveLen == 1:
            self.lutR = self.curvModeGetTable('rTRC')
            self.lutG = self.curvModeGetTable('gTRC')
            self.lutB = self.curvModeGetTable('bTRC')
        else:
            self.curveLerpR = None

        if self.trcType == 'curv' and self.curveLen == 1:
            rCont = self.extractICCtag(self.prf, b'rTRC')[12:]
            gCont = self.extractICCtag(self.prf, b'gTRC')[12:]
            bCont = self.extractICCtag(self.prf, b'bTRC')[12:]

            # rGamma = self.u8Fixed8NumberToFloat(rCont)
            # gGamma = self.u8Fixed8NumberToFloat(gCont)
            # bGamma = self.u8Fixed8NumberToFloat(bCont)

            self.rGamma = self.u8Fixed8NumberToFloat(rCont)
            self.gGamma = self.u8Fixed8NumberToFloat(gCont)
            self.bGamma = self.u8Fixed8NumberToFloat(bCont)

            gamma = self.u8Fixed8NumberToFloat(self.curveCont)
            self.gamma = gamma

        else:
            gamma = 1.0
            self.gamma = 1.0
            self.rGamma = 1.0
            self.gGamma = 1.0
            self.bGamma = 1.0

        self.vTRCParaToLinearSingle = vectorize(self.trcParaToLinearSingle)

    def trcDecodeToLinear(self, input):
        if self.trcType == 'curv':
            r = np.apply_along_axis(self.curveToLinearNP, 2, input, 0)
            g = np.apply_along_axis(self.curveToLinearNP, 2, input, 1)
            b = np.apply_along_axis(self.curveToLinearNP, 2, input, 2)
            rgb = np.stack((r, g, b), axis=-1)
            result = rgb
        elif self.trcType == 'para':
            r = np.apply_along_axis(self.trcParaToLinear, 2, input, 0, *self.rParaParams)
            g = np.apply_along_axis(self.trcParaToLinear, 2, input, 1, *self.gParaParams)
            b = np.apply_along_axis(self.trcParaToLinear, 2, input, 2, *self.bParaParams)
            rgb = np.stack((r, g, b), axis=-1)
            result = rgb
        else:
            result = 0
        return result

    def trcDecodeToLinearSingle(self, input):
        if self.trcType == 'curv':
            result = self.curveToLinearNPSingle(input)
        elif self.trcType == 'para':
            result = self.vTRCParaToLinearSingle(input, *self.paraParams)
        else:
            result = 0
        return result

    def curveToLinearNP(self, input: float, channel: int) -> float:
        if self.curveLen == 1:
            if channel == 0:
                gamma = self.rGamma
            elif channel == 1:
                gamma = self.gGamma
            elif channel == 2:
                gamma = self.bGamma
            calc = input[channel] ** gamma
            return calc
        else:
            if channel == 0:
                return np.interp(input[channel], self.lutR[0], self.lutR[1])
            elif channel == 1:
                return np.interp(input[channel], self.lutG[0], self.lutG[1])
            elif channel == 2:
                return np.interp(input[channel], self.lutB[0], self.lutB[1])

    def curveToLinearNPSingle(self, input: float) -> float:
        if self.curveLen == 1:
            gamma = self.rGamma
            calc = input ** gamma
            return calc
        else:
            return np.interp(input, self.lutR[0], self.lutR[1])

    def trcParaToLinear(self, x: float, channel: int, *args) -> float:
        if len(args) == 1:
            Y = pow(x[channel], args[0])
            return Y

        elif len(args) == 3:
            if x[channel] >= (-args[2] / args[1]):
                Y = pow(((args[1] * x[channel]) + args[2]), args[0])
            elif x[channel] < (-args[2] / args[1]):
                Y = 0
            return Y

        elif len(args) == 4:
            if x[channel] >= (-args[2] / args[1]):
                Y = pow(((args[1] * x[channel]) + args[2]), args[0]) + args[3]
            elif x[channel] < (-args[2] / args[1]):
                Y = args[3]
            return Y

        elif len(args) == 5:
            if x[channel] >= args[4]:
                Y = pow(((args[1] * x[channel]) + args[2]), args[0])
            elif x[channel] < args[4]:
                Y = (args[3] * x[channel])
            return Y

        elif len(args) == 7:
            if x[channel] >= args[4]:
                Y = pow(((args[1] * x[channel]) + args[2]), args[0]) + args[5]
            elif x[channel] < args[4]:
                Y = ((args[3] * x[channel]) + args[6])
            return Y

        else:
            return 0

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

    def curvModeGetTable(self, tag: str):
        prf = self.prf

        curveLen = int.from_bytes(self.extractICCtag(prf, tag.encode('utf-8'))[8:12], 'big')
        curveCont = self.extractICCtag(prf, tag.encode('utf-8'))[12:]

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

    def parametricParse(self, tag: str) -> list:
        paraParams = []

        if self.trcType == 'para':
            paraMode = int.from_bytes(self.extractICCtag(self.prf, tag.encode('utf-8'))[8:10], 'big')
            if paraMode == 0:
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[12:16]))
            elif paraMode == 1:
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[12:16]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[16:20]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[20:24]))
            elif paraMode == 2:
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[12:16]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[16:20]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[20:24]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[24:28]))
            elif paraMode == 3:
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[12:16]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[16:20]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[20:24]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[24:28]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[28:32]))
            elif paraMode == 4:
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[12:16]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[16:20]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[20:24]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[24:28]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[28:32]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[32:36]))
                paraParams.append(self.s15Fixed16NumberToFloat(self.extractICCtag(self.prf, tag.encode('utf-8'))[36:40]))
        else:
            paraMode = 0
        
        return paraParams
        
    def profileFromEmbed(self, pName = '') -> colour.RGB_Colourspace:
        prf = self.prf
        prfByte = self.prfByte

        pWhitepoint = prf.profile.media_white_point[1]
        pRedPrimary = prf.profile.red_colorant[1]
        pGreenPrimary = prf.profile.green_colorant[1]
        pBluePrimary = prf.profile.blue_colorant[1]

        pWhiteXYZ = np.array(prf.profile.media_white_point[0])

        pWhitexy = np.array(pWhitepoint)
        wt_pcs = np.array([0.34570292, 0.35853753])
        wt_d65 = np.array([0.31270049, 0.32900094])

        wt_prf_byte = self.extractICCtag(prf, b'wtpt')[8:]

        #coarse estimation of D50 wp on ICC profile as bytes
        wt_pcs_byte = b'\x00\x00\xF6\xD6\x00\x01\x00\x00\x00\x00\xD3\x2C'
        wt_pcs_byte2 = b'\x00\x00\xF6\xD6\x00\x01\x00\x00\x00\x00\xD3\x2D'

        #coarse estimation
        diff = round((pWhitexy[0] - wt_pcs[0]) * 100)

        if wt_prf_byte == wt_pcs_byte or wt_prf_byte == wt_pcs_byte2:
            wSame = True
            # print('whitepoint same')
        else:
            wSame = False
            # print('whitepoint different')
            pass

        if prf.profile.chromatic_adaptation and wSame:
            #use chromatic_adaptation tag if the profile has it
            #and skip if white point is already different from PCS (XYZ)
            pCA = np.array(prf.profile.chromatic_adaptation[0])
            pCAinv = inv(pCA)
            pWhiteCA = np.dot(pCAinv, pWhiteXYZ)
            pWhitexy = colour.XYZ_to_xy(pWhiteCA)
            wt_prf = pWhitexy
        else:
            #else, take from the media_white_point tag
            wt_prf = np.array([pWhitepoint[0], pWhitepoint[1]])

        if pName:
            p_Name = pName
        else:
            ps_Name = ImageCms.getProfileDescription(prf)
            p_Name = ps_Name.replace('.icc', '').replace('.icm', '').strip()

        pRGBD50 = np.array([pRedPrimary[0], pRedPrimary[1], pGreenPrimary[0], pGreenPrimary[1], pBluePrimary[0], pBluePrimary[1]])
        pRGBD65 = colour.chromatically_adapted_primaries(pRGBD50, wt_pcs, wt_prf, 'Bradford')

        colourspace = colour.RGB_Colourspace(p_Name, pRGBD65, wt_prf)

        return colourspace

    def u8Fixed8NumberToFloat(self, u: bytes) -> float:
        t = struct.unpack('>h', u)
        g = (2**-8) * t[0]
        return g

    def s15Fixed16NumberToFloat(self, s: bytes) -> float:
        t = struct.unpack('>l', s)
        g = (2**-16) * t[0]
        return g

    def extractICCtag(self, profile: ImageCms.ImageCmsProfile, byteToFind: bytes) -> bytes:
        prf = profile.tobytes()
        tagNdx = prf.find(byteToFind)
        tagPosNdx = int.from_bytes(prf[tagNdx+4:tagNdx+8], 'big')
        tagLen = int.from_bytes(prf[tagNdx+8:tagNdx+12], 'big')

        tagContent = prf[tagPosNdx:tagPosNdx+tagLen]

        return tagContent
