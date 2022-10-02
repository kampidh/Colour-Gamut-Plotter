from logging import raiseExceptions
import struct
from PIL import ImageCms

import colour
import numpy as np
from numpy import vectorize

from numpy.linalg import inv

import concurrent.futures

class iccToTRC:
    def __init__(self, profile: ImageCms.ImageCmsProfile):
        self.prf = profile
        self.prfByte = profile.tobytes()
        self.prfVer = profile.profile.version

        ps_Name = ImageCms.getProfileDescription(self.prf)
        p_Name = ps_Name.replace('.icc', '').replace('.icm', '').strip()

        self.prfName = p_Name

        self.trcType = self.extractICCtag('rTRC')[0:4].decode('utf-8').strip()

        self.curveLen = int.from_bytes(self.extractICCtag('rTRC')[8:12], 'big')
        self.curveCont = self.extractICCtag('rTRC')[12:]

        self.paraParams = []
        self.paraMode = 0

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

        self.vTRCParaToLinearSingle = vectorize(self.trcParaToLinearSingle)

    def trcDecode(self, input):
        if self.uniformTRC:
            result = self.trcDecodeToLinearSingle(input)
        else:
            result = self.trcDecodeToLinear_MP(input)
        return result

    def trcDecodeToLinear_MP(self, input):
        inRGB = [input[...,0], input[...,1], input[...,2]]
        bufRGB = [None] * 3

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for x in range(3):
                if self.trcTypes[x] == 'curv':
                    bufRGB[x] = executor.submit(self.curveToLinearNP_Single, inRGB[x], x)
                elif self.trcTypes[x] == 'para':
                    bufRGB[x] = executor.submit(self.vTRCParaToLinearSingle, inRGB[x], *self.trcParaParams[x])
                else:
                    raise Exception(f'TRC type {self.trcTypes[x]} is not supported')

        r = bufRGB[0].result()
        g = bufRGB[1].result()
        b = bufRGB[2].result()
        rgb = np.stack((r, g, b), axis=-1)
        result = rgb
        
        return result

    def trcDecodeToLinear_SP(self, input):
        inRGB = [input[...,0], input[...,1], input[...,2]]
        bufRGB = [None] * 3

        for x in range(3):
            if self.trcTypes[x] == 'curv':
                bufRGB[x] = self.curveToLinearNP_Single(inRGB[x], x)
            elif self.trcTypes[x] == 'para':
                bufRGB[x] = self.vTRCParaToLinearSingle(inRGB[x], *self.trcParaParams[x])
        
        r = bufRGB[0]
        g = bufRGB[1]
        b = bufRGB[2]
        rgb = np.stack((r, g, b), axis=-1)
        result = rgb

        return result

    def trcDecodeToLinearSingle(self, input):
        if self.trcTypes[0] == 'curv':
            result = self.curveToLinearNP_Single(input, 0)
        elif self.trcTypes[0] == 'para':
            result = self.vTRCParaToLinearSingle(input, *self.trcParaParams[0])
        return result

    def curveToLinearNP_Single(self, input: float, channel: int) -> float:
        if self.trcCurvLens[channel] == 1:
            # gamma = self.trcCurvGammas[channel]
            calc = input ** self.trcCurvGammas[channel]
            return calc
        else:
            return np.interp(input, self.trcCurvLUTs[channel][0], self.trcCurvLUTs[channel][1])

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
        # prf = self.prf

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
        
    def profileFromEmbed(self, pName = '') -> colour.RGB_Colourspace:

        pRedPrimary = colour.XYZ_to_xy(self.extractXYZdata('rXYZ'))
        pGreenPrimary = colour.XYZ_to_xy(self.extractXYZdata('gXYZ'))
        pBluePrimary = colour.XYZ_to_xy(self.extractXYZdata('bXYZ'))

        wt_pcs = np.array([0.34570292, 0.35853753])
        wt_d65 = np.array([0.31270049, 0.32900094])

        if self.extractICCtag('chad') != -1:
            chAD_mtx = self.extractSF32data('chad')
            chad_exist = True
        else:
            chad_exist = False

        pcsWhite_XYZ = self.extractXYZPCS()
        pWhite_XYZ = self.extractXYZdata('wtpt')

        sinMTX = np.array([[1,0,0],[0,1,0],[0,0,1]], dtype=float)

        if chad_exist and not np.all(chAD_mtx == sinMTX):
            #use chromatic_adaptation tag if the profile has it
            #and skip if white point is already different from PCS (XYZ)
            pCAinv = inv(chAD_mtx)
            pWhiteCA = np.dot(pCAinv, pWhite_XYZ)
            pWhitexy = colour.XYZ_to_xy(pWhiteCA)
            wt_prf = pWhitexy
        else:
            #else, take from the media_white_point tag
            wt_prf = colour.XYZ_to_xy(pWhite_XYZ)


        if pName:
            p_Name = pName
        else:
            ps_Name = ImageCms.getProfileDescription(self.prf)
            p_Name = ps_Name.replace('.icc', '').replace('.icm', '').strip()

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
            return 0

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
            return 0

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
            # raise  Exception('Cannot find selected tag in tags list')
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

    def validate(self):

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