#================================================================================
#   CIE Colour Gamut Plotter
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

import os, sys
import posixpath
import time
from PyQt5 import QtWidgets, QtGui, uic
from PyQt5.QtWidgets import QFileDialog, QMessageBox
from PyQt5.QtCore import Qt

import colour
from colour.plotting import *
import matplotlib.pyplot as plt
from pathlib import Path

import numpy as np
from math import floor

# from PIL import Image
# from tifffile import TiffFile
import cv2
import pyvips

# Workaround for big profile size in png files
# from PIL import PngImagePlugin
# maxchunk = 5
# PngImagePlugin.MAX_TEXT_CHUNK = maxchunk * (1024**2)

# Workaround for pyinstaller not showing the pyplot window
import matplotlib
matplotlib.use('TkAgg')
# matplotlib.use('QtAgg')

from icctotrcMP import iccToTRC
import vispy.plot as vp

try:
    from ctypes import windll  # Windows only
    myappid = 'Kampidh.Colour Gamut Plotter.CIE Plotter.v1_3b'
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except ImportError:
    pass

basedir = os.path.dirname(__file__)
mainuifile = os.path.join(basedir,'MainUIwindow.ui')

winVer = '1.3b'
winTitle = 'Colour Gamut Plotter v' + winVer

aboutText = '''
2022 - Written by Kampidh<br>
Licensed under GPL-3.0<br>
Build with Python, PyQt, OpenCV, and <a href="https://www.colour-science.org/">Colour Science</a><br>
Also Numpy, Pyvips, and Vispy.<br>
<br>
<a href="https://github.com/kampidh/Colour-Gamut-Plotter">Github Project Page</a>
'''

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        uic.loadUi(mainuifile, self)

        self.file_input = self.findChild(QtWidgets.QLineEdit, 'FileDirectoryInput')
        self.log_output = self.findChild(QtWidgets.QPlainTextEdit, 'LogOutputText')
        self.output_dir = self.findChild(QtWidgets.QLineEdit, 'SaveDirectoryInput')
        self.output_btn = self.findChild(QtWidgets.QPushButton, 'SaveDirectoryButton')
        self.apply_btn = self.findChild(QtWidgets.QPushButton, 'ApplyButton')
        self.save_checkbox = self.findChild(QtWidgets.QCheckBox, 'SaveAsCheckbox')
        self.colorspace_combo = self.findChild(QtWidgets.QComboBox, 'ColorspaceCombo')
        self.colorspace_linear = self.findChild(QtWidgets.QCheckBox, 'ColorspaceLinearCheckbox')
        self.plotdensity_combo = self.findChild(QtWidgets.QComboBox, 'PlotDensityCombo')
        self.diagramtype_combo = self.findChild(QtWidgets.QComboBox, 'DiagramTypeCombo')
        self.usealltags_checkbox = self.findChild(QtWidgets.QCheckBox, 'useAllTagsCheckbox')
        self.hiressize_spin = self.findChild(QtWidgets.QSpinBox, 'HiresSizeSpinBox')
        self.extragamut_checkbox = self.findChild(QtWidgets.QCheckBox, 'extraGamutCheckbox')

        # Debug checkbox
        # self.usealltags_checkbox.setVisible(False)

        self.setWindowTitle(winTitle)

        self.printLog('==---------------------------------==\n')

    def closeEvent(self, event):
        plt.close()

    def dragEnterEvent(self, event):
        event.accept()
        # if event.mimeData().hasImage:
        #     event.accept()
        # else:
        #     event.ignore()

    def dragMoveEvent(self, event):
        event.accept()
        # if event.mimeData().hasImage:
        #     event.accept()
        # else:
        #     event.ignore()

    def dropEvent(self, event):
        event.setDropAction(Qt.CopyAction)
        file_path = event.mimeData().urls()[0].toLocalFile()
        self.file_input.setText(file_path)
        event.accept()

    def ColorspaceCombo_changed(self):
        if self.colorspace_combo.currentIndex() == 0:
            self.colorspace_linear.setEnabled(False)
        else:
            self.colorspace_linear.setEnabled(True)

    def FileOpenButton_clicked(self):
        hmDir = str(Path.home())
        fInput = self.file_input.text()
        options = QFileDialog.Options()
        if not fInput:
            fileName, _ = QFileDialog.getOpenFileName(self,"Select Image...", hmDir,"Image Files (*.png *.jpg *.jxl *.jfif *.tif *.tiff *.bmp);;All Files (*)", options=options)
        else:
            fDir = str(os.path.dirname(fInput))
            if os.path.isdir(fDir):
                fileName, _ = QFileDialog.getOpenFileName(self,"Select Image...", fDir,"Image Files (*.png *.jpg *.jxl *.jfif *.tif *.tiff *.bmp);;All Files (*)", options=options)
            else:
                fileName, _ = QFileDialog.getOpenFileName(self,"Select Image...", hmDir,"Image Files (*.png *.jpg *.jxl *.jfif *.tif *.tiff *.bmp);;All Files (*)", options=options)
        if fileName:
            self.file_input.setText(fileName)

    def SaveDirectoryButton_clicked(self):
        hmDir = str(Path.home())
        fOutput = self.output_dir.text()
        options = QFileDialog.Options()
        if not fOutput:
            directoryName = QFileDialog.getExistingDirectory(self,"Select Save Folder...", hmDir, options=options)
        else:
            fDir = str(fOutput)
            if os.path.isdir(fDir):
                directoryName = QFileDialog.getExistingDirectory(self,"Select Save Folder...", fDir, options=options)
            else:
                directoryName = QFileDialog.getExistingDirectory(self,"Select Save Folder...", hmDir, options=options)
        if directoryName:
            self.output_dir.setText(directoryName)

    def PlotDensityCombo_changed(self):
        plotdensity_index = self.plotdensity_combo.currentIndex()
        if plotdensity_index == 0:
            maxPixel = 50000
        elif plotdensity_index == 1:
            maxPixel = 100000
        elif plotdensity_index == 2:
            maxPixel = 500000
        elif plotdensity_index == 3:
            maxPixel = 1000000
        elif plotdensity_index == 4:
            maxPixel = 3000000
        elif plotdensity_index == 5:
            maxPixel = 5000000
        else:
            maxPixel = 'Maximum'

        self.printLog('Selected plot density:')
        if plotdensity_index != 6:
            self.printLog('Max size: %s pixels' % maxPixel)
        else:
            self.printLog('Max size: No size limit')
            self.printLog('Be careful as it may hang your system if your image is huge!')
        self.printLog('')

    def SaveAsCheckbox_changed(self):
        if self.save_checkbox.isChecked():
            self.output_btn.setEnabled(True)
            self.output_dir.setEnabled(True)
            self.hiressize_spin.setEnabled(True)
        else:
            self.output_btn.setEnabled(False)
            self.output_dir.setEnabled(False)
            self.hiressize_spin.setEnabled(False)

    def AboutButton_clicked(self):
        abt = QMessageBox()
        abt.setTextFormat(Qt.RichText)
        abt.setText(aboutText)
        abt.setWindowTitle('About')
        abt.setStandardButtons(QMessageBox.Ok)
        abt.exec_()

    def Apply_clicked(self):
        
        if not self.file_input.text():
            QMessageBox.warning(self, 'Error', 'Input filename cannot be empty')
            return

        if not os.path.isfile(self.file_input.text()):
            QMessageBox.warning(self, 'Error', 'Input filename invalid or not exist')
            return

        if self.plotdensity_combo.currentIndex() == 6:
            repNoResize = QMessageBox.question(self, 'Warning', 'Are you sure you want to proceed without resizing?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if repNoResize == QMessageBox.No:
                return

        if self.save_checkbox.isChecked() and self.output_dir.text():
            if not os.path.isdir(self.output_dir.text()):
                QMessageBox.warning(self, 'Error', 'Output directory invalid or not exist')
                return

        
        self.apply_btn.setEnabled(False)

        input_file = self.file_input.text()
        colorspace_index = self.colorspace_combo.currentIndex()
        colorspace_isLinear = self.colorspace_linear.isChecked()
        plotdensity_index = self.plotdensity_combo.currentIndex()
        diagramtype_index = self.diagramtype_combo.currentIndex()
        saveOnly_checked = self.save_checkbox.isChecked()
        saveOutput_dir = self.output_dir.text()
        hires_size = self.hiressize_spin.value() / 100

        # debug
        useAllTRCTags = self.usealltags_checkbox.isChecked()
        extraGamut = self.extragamut_checkbox.isChecked()

        colorspace = ''
        diagramtype = ''
        dontResize = False
        autoClspc = False

        maxPixel = 500000

        chRange1931 = [-0.1, 0.85, -0.05, 0.9]
        chRange1976 = [-0.05, 0.65, -0.05, 0.65]

        pltSize = [10, 10]

        prep = ''
        stinfo = ''
        infostr = ''

        scAlpha = 0.9
        cProfile = ''
        trcFunc = 'sRGB'
        autoProfileValid = False

        if colorspace_index == 0:
            colorspace = 'Auto'
            autoClspc = True
        elif colorspace_index == 1:
            colorspace = 'sRGB'
        elif colorspace_index == 2:
            colorspace = 'ITU-R BT.2020'
        elif colorspace_index == 3:
            colorspace = 'Display P3'
        elif colorspace_index == 4:
            colorspace = 'adobe1998'
        elif colorspace_index == 5:
            colorspace = 'ITU-R BT.2020'
            trcFunc = 'ITU-R BT.2100 PQ'
        elif colorspace_index == 6:
            colorspace = 'ITU-R BT.2020'
            trcFunc = 'ITU-R BT.2100 HLG'

        if diagramtype_index == 0:
            diagramtype = 'CIE-1931'
        elif diagramtype_index == 1:
            diagramtype = 'CIE-1976-UCS'

        if plotdensity_index == 6:
            dontResize = True

        if plotdensity_index == 0:
            maxPixel = 50000
        elif plotdensity_index == 1:
            maxPixel = 100000
        elif plotdensity_index == 2:
            maxPixel = 500000
        elif plotdensity_index == 3:
            maxPixel = 1000000
        elif plotdensity_index == 4:
            maxPixel = 3000000
        elif plotdensity_index == 5:
            maxPixel = 5000000
        else:
            maxPixel = 500000

        if input_file.find('.tif') != -1 or input_file.find('.tiff') != -1 :
            isTIFF = True
        else:
            isTIFF = False

        if input_file.find('.exr') != -1 :
            colorspace_isLinear = True

        self.printLog('Diagram style: %s' % diagramtype)
        self.printLog('Save file: %s' % saveOnly_checked)
        self.printLog('Input image: %s' % input_file)
        # self.printLog('Is Linear?: %s' % colorspace_isLinear)
        # self.printLog('No resize?: %s' % dontResize)
        self.printLog('Plotting Density: %s' % plotdensity_index)
        if not dontResize:
            self.printLog('Max Pixel count: %i pixels' % maxPixel)
        self.printLog('Color Space: %s' % colorspace + '\n')

        stdPlotSize = 12

        if saveOnly_checked:
            # pltSize = [25, 25]
            pltSize = [hires_size, hires_size]
        else:
            pltSize = [stdPlotSize, stdPlotSize]

        fontSize = 10 * (hires_size / stdPlotSize)

        stinfo = ''

        # try:
        #     if isTIFF:
        #         # use tifffile to extract data from tiff file
        #         tif = TiffFile(input_file)
        #         prep_a = tif.pages[0].asarray()
        #         stinfo = tif.pages[0].tags['InterColorProfile'].value
        #         tif.close()
        #         prep = cv2.cvtColor(prep_a, cv2.COLOR_RGB2BGR)
        #     else:
        #         # use PIL instead for other images
        #         im = Image.open(input_file)
        #         # im.load()
        #         # print(im.info)
        #         stinfo = im.info.get('icc_profile')
        #         im.close()
        #         prep = cv2.imread(input_file,-1)

        #     prepd = prep.dtype

        try:
            tA = time.perf_counter()
            image = pyvips.Image.new_from_file(input_file, access='sequential')
            tB = time.perf_counter()
            self.printLog(f'Image loaded in {round((tB-tA) * 1000, 2)} milisecond(s)')
            prep_a = image.numpy()
            stinfo = image.get('icc-profile-data')
            if isTIFF and (prep_a.dtype == 'float32' or prep_a.dtype == 'float16'):
                # float tiff files are blown out somehow by pyvips/libvips
                prep = cv2.cvtColor(prep_a/255, cv2.COLOR_RGB2BGR)
            else:
                prep = cv2.cvtColor(prep_a, cv2.COLOR_RGB2BGR)

            prepd = prep.dtype
            
        except:
            self.printLog('Failed to read color metadata, try to read raw data instead')
            try:
                image = pyvips.Image.new_from_file(input_file, access='sequential')
                prep_a = image.numpy()
                if isTIFF:
                    prep = cv2.cvtColor(prep_a/255, cv2.COLOR_RGB2BGR)
                else:
                    prep = cv2.cvtColor(prep_a, cv2.COLOR_RGB2BGR)
                # prep = cv2.imread(input_file,-1)
                prepd = prep.dtype
            except:
                self.printLog('Failed to open file, not a valid or unsupported image format')
                self.printLog('\n==---------------------------------==\n')
                self.apply_btn.setEnabled(True)
                return


        if stinfo and autoClspc:

            autoProfileValid = True

            self.printLog('Automatic colorspace detection active')

            # give it the byte stream of extracted icc data
            # either from PIL or tifffile
            try:
                customProfile = iccToTRC(stinfo)
                infostr = customProfile.extractDescription()
                cSpace = customProfile.extractColorSpace()
                # pValidate = customProfile.validate() # Deprecated, unused outside the module
            except Exception as e:
                cSpace = 'RGB'
                autoProfileValid = False
                self.printLog('\n' + str(e))
                self.printLog('Color profile reading error, using sRGB instead')
                cProfile = 'sRGB'
                trcFunc = 'sRGB'
            
            colorType = cSpace
            if colorType != 'RGB':
                self.printLog('\n%s is not supported. Use RGB image instead' % colorType)
                self.printLog('\n==---------------------------------==\n')
                self.apply_btn.setEnabled(True)
                return

            # Deprecated, unused
            # if not pValidate:
            #     autoProfileValid = False
            #     self.printLog('\nColor profile reading error, using sRGB instead')
            #     cProfile = 'sRGB'
            #     trcFunc = 'sRGB'

        else:
            autoProfileValid = False
            if autoClspc:
                self.printLog('Automatic colorspace detection active')
                self.printLog('No color profile found, using sRGB instead')
                cProfile = 'sRGB'
                trcFunc = 'sRGB'
            else:
                cProfile = colorspace
                # trcFunc = 'sRGB'

        np.seterr(divide='ignore', invalid='ignore')
        
        self.printLog("\nImage bitdepth: %s" % prepd)
        self.printLog("width: %s | height: %s" % (prep.shape[1], prep.shape[0]))
       
        imStartSize = prep.shape[0] * prep.shape[1]
        self.printLog("Input pixel count: %i pixels | %.3f MPixels" % (imStartSize, imStartSize / 1000000))

        if (prep.shape[0] * prep.shape[1]) > maxPixel and dontResize == False:

            reduxRatio = np.sqrt((prep.shape[0] * prep.shape[1]) / maxPixel)

            self.printLog("Reduction ratio = 1:%.3f" % reduxRatio)

            prep = cv2.resize(prep, (floor(prep.shape[1] / reduxRatio), floor(prep.shape[0] / reduxRatio)), interpolation=6)
            # self.printLog("Resized:")
            self.printLog("width: %s | height: %s" % (prep.shape[1], prep.shape[0]))

            finSize = prep.shape[0] * prep.shape[1]
            self.printLog("Final pixel count: %i pixels | %.3f MPixels" % (finSize, finSize / 1000000))

        imSize = prep.shape[0] * prep.shape[1]


        if imSize <= 50000:
            scAlpha = 0.9
        elif imSize <= 100000:
            scAlpha = 0.8
        elif imSize <= 500000:
            scAlpha = 0.5
        elif imSize <= 1000000:
            scAlpha = 0.25
        elif imSize <= 3000000:
            scAlpha = 0.2
        elif imSize <= 5000000:
            scAlpha = 0.15
        else:
            scAlpha = 0.1

        img = cv2.cvtColor(prep, cv2.COLOR_BGR2RGB)

        RGB = colour.io.convert_bit_depth(img)


        if autoProfileValid:
            cProfile = customProfile.profileFromEmbed()

            self.printLog('\nUsing embedded profile gamut and TRC')
            self.printLog('Name: %s' % customProfile.prfName)
            self.printLog('ICC version: %.2f' % customProfile.prfVer)
            wtpoint = customProfile.prfWhite
            self.printLog(f'Profile whitepoint: x:{round(wtpoint[0], 6)}, y:{round(wtpoint[1], 6)}')
            trcType = customProfile.trcType

            if trcType == 'curv':
                self.printLog('TRC type: Curves')
                curveLen = customProfile.curveLen
                self.printLog('Length: %i' % curveLen)
                if curveLen == 1:
                    self.printLog('Gamma: %.6f' % customProfile.gamma)

            elif trcType == 'para':
                self.printLog('TRC type: Parametric\nValues:')
                paraParams = ''.join(str(customProfile.paraParams))
                self.printLog(paraParams)

            elif trcType == 'A2B0 mAB':
                self.printLog('TRC type: A2B0 mAB')

            elif trcType == 'A2B0 mft2':
                self.printLog('TRC type: A2B0 mft2')

            if not customProfile.prfPCS_white_check:
                self.printLog('Warning: Embedded profile PCS illuminant is not D50')

            if not cProfile:
                self.printLog('\n==---------------------------------==')
                self.printLog('Plotting Failed')
                if 'identity'.lower() in infostr.lower():
                    self.printLog('IdentityRGB is not supported.')
                else:
                    self.printLog('Current color profile is not supported.')
                self.printLog('==---------------------------------==\n')
                return

            if customProfile.uniformTRC:
                self.printLog('TRC is uniform between channels.\nCalculate using single TRC.')
            else:
                self.printLog('TRC is not uniform between channels.\nCalculate using all TRC instead.')

            tA = time.perf_counter()

            RGBlin = customProfile.trcDecode(RGB)
            # RGBlin = np.clip(RGBlin, 0.0, 1024.0)

            tB = time.perf_counter()
            self.printLog(f'Image TRC decoded in {round(tB-tA, 4)} second(s)')
            
            # debug
            # if useAllTRCTags:
            #     print('Multithread')
            #     RGBlin = customProfile.trcDecodeToLinear_MP(RGB)
            # else:
            #     print('Singlethread')
            #     RGBlin = customProfile.trcDecodeToLinearSingle(RGB)

            # tB = time.perf_counter()
            # self.printLog(f'Image TRC decoded in {round(tB-tA, 4)} second(s)')

            if np.any(RGBlin > 1.0):
                self.printLog('Detected pixel value with >1.0, possibly an HDR image')

        else:
            tA = time.perf_counter()
            if colorspace_index < 5:
                RGBlin = colour.cctf_decoding(RGB, function=trcFunc)
            else:
                # HDR PQ and HLG
                RGBlin = colour.oetf_inverse(RGB, function=trcFunc)
            tB = time.perf_counter()
            self.printLog(f'Image TRC decoded in {round(tB-tA, 4)} second(s)')

        # print(np.amin(RGBlin))
        if useAllTRCTags and colorspace_index == 0:
            srgb = colour.models.RGB_COLOURSPACE_sRGB
            wtpnt = None
            if autoProfileValid:
                XYZlin = colour.RGB_to_XYZ(RGBlin, customProfile.prfWhite, customProfile.prfWhite, cProfile.matrix_RGB_to_XYZ)
                xyYlin = colour.XYZ_to_xy(XYZlin)
                wtpnt = customProfile.prfWhite
                xyY2lin = xyYlin.reshape(-1, xyYlin.shape[-1])
                xyYprim = customProfile.primariesCA
                xyYprim = np.append(xyYprim, [xyYprim[0]], axis=0)
            else:
                wtpnt = srgb.whitepoint
                XYZlin = colour.RGB_to_XYZ(RGBlin, srgb.whitepoint, srgb.whitepoint, srgb.matrix_RGB_to_XYZ)
                xyYlin = colour.XYZ_to_xy(XYZlin)
                xyY2lin = xyYlin.reshape(-1, xyYlin.shape[-1])

            sRGBprim = srgb.primaries
            sRGBprim = np.append(sRGBprim, [sRGBprim[0]], axis=0)

            bord = np.array([
                [0,0],
                [0,0.85],
                [0.85,0.85],
                [0.85,0],
                [0,0]
            ])

            color = (0.0, 0.0, 1.0)
            fig = vp.Fig(show=False)
            fig.size = (1200, 1200)
            # fig.bgcolor = (0.5, 0.5, 0.5)
            line = fig[0, 0].plot(xyY2lin, symbol='o', width=0,
                                    face_color=color + (scAlpha/10,),
                                    edge_color=None,
                                    marker_size=4,)
            line.set_gl_state(depth_test=False)

            if autoProfileValid:
                fig[0, 0].plot(xyYprim, symbol='o', width=1,
                                        face_color='k',
                                        edge_color='k',
                                        marker_size=4,)

            fig[0, 0].plot(sRGBprim, symbol='o', width=1,
                                    color='m',
                                    face_color='m',
                                    edge_color='m',
                                    marker_size=4,)
            fig[0, 0].plot([wtpnt], symbol='o', width=1,
                                    color='w',
                                    face_color='w',
                                    edge_color='k',
                                    marker_size=8,)
            fig[0, 0].plot(bord, symbol='o', width=1,
                                    face_color='k',
                                    edge_color='k',
                                    marker_size=4,)
            fig.show(run=True)

            self.apply_btn.setEnabled(True)
            self.printLog('\n==---------------------------------==')
            return

        if (extraGamut):
            ovrSpace = [cProfile, 'sRGB', 'Display P3', 'ITU-R BT.2020']
        else:
            ovrSpace = [cProfile, 'sRGB']

        if saveOnly_checked:
            plotDens_name = ''
            if plotdensity_index == 6:
                plotDens_name = 'Full'
            else:
                plotDens_name = plotdensity_index
            outFileName = os.path.splitext(os.path.basename(input_file))[0] + '_CIEPlot_' + diagramtype + '_size-%s' % plotDens_name + '.png'
            
            if not saveOutput_dir:
                try:
                    newHomeDir = os.path.join(Path.home() , 'Pictures' , 'CIEPlot_Output')

                    if not os.path.exists(newHomeDir):
                        os.makedirs(newHomeDir)
                    fiName = os.path.join(newHomeDir, outFileName)
                except:
                    self.printLog('Failed to create a folder to save image')
                    self.apply_btn.setEnabled(True)
                    return
            else:
                fName = os.path.join(saveOutput_dir, outFileName)
                fiName = fName.replace(os.sep, posixpath.sep)
        else:
            self.apply_btn.setEnabled(True)

        self.printLog('\n==---------------------------------==')
        sSuccess = False


        #--------Here goes the plotting code--------------
        if diagramtype == 'CIE-1931':

            COL_STYLE = colour.plotting.colour_style()

            if saveOnly_checked:
                COL_STYLE.update(
                    {
                        "grid.alpha": 0.25,
                        "legend.framealpha": 0.75,
                        "legend.loc": 'lower center',
                        "figure.figsize": pltSize,
                        "legend.facecolor": '#202020',
                        "font.size": fontSize * 0.85,
                    }
                )
            else:
                COL_STYLE.update(
                    {
                        "grid.alpha": 0.25,
                        "legend.framealpha": 0.75,
                        "legend.loc": 'lower center',
                        "figure.figsize": pltSize,
                        "legend.facecolor": '#202020',
                    }
                )

            plt.style.use(COL_STYLE)
            plt.style.use("dark_background")

            if saveOnly_checked:
                try:
                    self.printLog('Saving image, please wait...')
                    plot_RGB_chromaticities_in_chromaticity_diagram_CIE1931(
                        RGBlin[...,0:3] if colorspace_isLinear == False or autoProfileValid == True else RGB[...,0:3],
                        cProfile,
                        colourspaces=ovrSpace,
                        spectral_locus_colours="RGB",
                        spectral_locus_opacity=0.75,
                        diagram_colours=[0.75, 0.75, 0.75],
                        diagram_opacity=0.15,
                        scatter_kwargs={'s':2, 'alpha':scAlpha},
                        title=f'CIE 1931 Diagram | {os.path.basename(input_file)}',
                        transparent_background=False,
                        bounding_box=chRange1931,
                        filename=fiName,
                    )
                    sSuccess = True
                    plt.close()
                except:
                    sSuccess = False
                    plt.close()
            else:
                try:
                    plot_RGB_chromaticities_in_chromaticity_diagram_CIE1931(
                        RGBlin[...,0:3] if colorspace_isLinear == False or autoProfileValid == True else RGB[...,0:3],
                        cProfile,
                        colourspaces=ovrSpace,
                        spectral_locus_colours="RGB",
                        spectral_locus_opacity=0.75,
                        diagram_colours=[0.75, 0.75, 0.75],
                        diagram_opacity=0.15,
                        scatter_kwargs={'s':2, 'alpha':scAlpha},
                        title=f'CIE 1931 Diagram | {os.path.basename(input_file)}',
                        transparent_background=False,
                        bounding_box=chRange1931,
                    )
                    self.printLog('Plotting Completed')
                    self.printLog('==---------------------------------==\n')
                except:
                    self.printLog('Plotting Failed')
                    if 'identity'.lower() in infostr.lower():
                        self.printLog('IdentityRGB is not supported.')
                    elif cProfile == '':
                        self.printLog('Current color profile is not supported.')
                    self.printLog('==---------------------------------==\n')
                    plt.close()
        elif diagramtype == 'CIE-1976-UCS':
            COL_STYLE = colour.plotting.colour_style()
            
            if saveOnly_checked:
                COL_STYLE.update(
                    {
                        "grid.alpha": 0.25,
                        "legend.framealpha": 0.75,
                        "legend.loc": 'lower left',
                        "figure.figsize": pltSize,
                        "legend.facecolor": '#202020',
                        "font.size": fontSize * 0.85,
                    }
                )
            else:
                COL_STYLE.update(
                    {
                        "grid.alpha": 0.25,
                        "legend.framealpha": 0.75,
                        "legend.loc": 'lower left',
                        "figure.figsize": pltSize,
                        "legend.facecolor": '#202020',
                    }
                )

            plt.style.use(COL_STYLE)
            plt.style.use("dark_background")

            if saveOnly_checked:
                try:
                    self.printLog('Saving image, please wait...')
                    plot_RGB_chromaticities_in_chromaticity_diagram_CIE1976UCS(
                        RGBlin[...,0:3] if colorspace_isLinear == False or autoProfileValid == True else RGB[...,0:3],
                        cProfile,
                        colourspaces=ovrSpace,
                        spectral_locus_colours="RGB",
                        spectral_locus_opacity=0.75,
                        diagram_colours=[0.75, 0.75, 0.75],
                        diagram_opacity=0.15,
                        scatter_kwargs={'s':2, 'alpha':scAlpha},
                        title=f'CIE 1976 UCS Diagram | {os.path.basename(input_file)}',
                        transparent_background=False,
                        bounding_box=chRange1976,
                        filename=fiName,
                    )
                    sSuccess = True
                    plt.close()
                except:
                    sSuccess = False
                    plt.close()
            else:
                try:
                    plot_RGB_chromaticities_in_chromaticity_diagram_CIE1976UCS(
                        RGBlin[...,0:3] if colorspace_isLinear == False or autoProfileValid == True else RGB[...,0:3],
                        cProfile,
                        colourspaces=ovrSpace,
                        spectral_locus_colours="RGB",
                        spectral_locus_opacity=0.75,
                        diagram_colours=[0.75, 0.75, 0.75],
                        diagram_opacity=0.15,
                        scatter_kwargs={'s':2, 'alpha':scAlpha},
                        title=f'CIE 1976 UCS Diagram | {os.path.basename(input_file)}',
                        transparent_background=False,
                        bounding_box=chRange1976,
                    )
                    self.printLog('Plotting Completed')
                    self.printLog('==---------------------------------==\n')
                except:
                    self.printLog('Plotting Failed')
                    if 'identity'.lower() in infostr.lower():
                        self.printLog('IdentityRGB is not supported.')
                    elif cProfile == '':
                        self.printLog('Current color profile is not supported.')
                    self.printLog('\n==---------------------------------==\n')
                    plt.close()
        else:
            self.printLog('Method invalid')
            self.printLog('\n==---------------------------------==\n')

        if saveOnly_checked:
            self.apply_btn.setEnabled(True)
            if sSuccess:
                self.printLog('Save completed')
                self.printLog(fiName)
            else:
                self.printLog('Save failed, directory invalid or no permission')
            self.printLog('\n==---------------------------------==\n')


    def printLog(self, logtxt):
        self.log_output.appendPlainText(logtxt)
        QtGui.QGuiApplication.processEvents()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon(os.path.join(basedir, 'gamuticon.ico')))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()