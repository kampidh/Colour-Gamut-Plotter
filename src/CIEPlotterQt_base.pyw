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
from PyQt5 import QtWidgets, QtGui, uic
from PyQt5.QtWidgets import QFileDialog, QMessageBox
from PyQt5.QtCore import Qt

import colour
from colour.plotting import *
import matplotlib.pyplot as plt
from pathlib import Path

import numpy as np
from math import floor

from PIL import Image, ImageCms
import io
import cv2

try:
    from ctypes import windll  # Only exists on Windows.
    myappid = 'Kampidh.Colour Gamut Plotter.CIE Plotter.v1'
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except ImportError:
    pass

basedir = os.path.dirname(__file__)
mainuifile = os.path.join(basedir,'MainUIwindow.ui')

winVer = '1.0'
WindowTitle = 'Colour Gamut Plotter v' + winVer

aboutText = '''
2022 - Written by Kampidh<br>
Licensed under GPL<br>
Build with Python, PyQt, OpenCV, and <a href="https://www.colour-science.org/">Colour Science</a><br>
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
        self.save_checkbox = self.findChild(QtWidgets.QCheckBox, 'SaveAsCheckbox')
        self.colorspace_combo = self.findChild(QtWidgets.QComboBox, 'ColorspaceCombo')
        self.colorspace_linear = self.findChild(QtWidgets.QCheckBox, 'ColorspaceLinearCheckbox')
        self.plotdensity_combo = self.findChild(QtWidgets.QComboBox, 'PlotDensityCombo')
        self.diagramtype_combo = self.findChild(QtWidgets.QComboBox, 'DiagramTypeCombo')

        self.setWindowTitle(WindowTitle)

        self.printLog('==---------------------------------==')

    def closeEvent(self, event):
        plt.close()

    def dragEnterEvent(self, event):
        if event.mimeData().hasImage:
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasImage:
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasImage:
            event.setDropAction(Qt.CopyAction)
            file_path = event.mimeData().urls()[0].toLocalFile()
            try:
                prep = cv2.imread(file_path,-1)
                im = Image.open(file_path)
                if im:
                    im.close()
                prepd = prep.dtype
            except:
                self.file_input.clear()
                QMessageBox.warning(self, 'Error', 'Unsupported format')
                event.ignore()
                return
            self.file_input.setText(file_path)
            event.accept()
        else:
            event.ignore()

    def FileOpenButton_clicked(self):
        hmDir = str(Path.home())
        fInput = self.file_input.text()
        options = QFileDialog.Options()
        if not fInput:
            fileName, _ = QFileDialog.getOpenFileName(self,"Select Image...", hmDir,"Image Files (*.png *.jpg *.bmp);;All Files (*)", options=options)
        else:
            fDir = str(os.path.dirname(fInput))
            if os.path.isdir(fDir):
                fileName, _ = QFileDialog.getOpenFileName(self,"Select Image...", fDir,"Image Files (*.png *.jpg *.bmp);;All Files (*)", options=options)
            else:
                fileName, _ = QFileDialog.getOpenFileName(self,"Select Image...", hmDir,"Image Files (*.png *.jpg *.bmp);;All Files (*)", options=options)
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
        else:
            self.output_btn.setEnabled(False)
            self.output_dir.setEnabled(False)

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

        input_file = self.file_input.text()
        colorspace_index = self.colorspace_combo.currentIndex()
        colorspace_isLinear = self.colorspace_linear.isChecked()
        plotdensity_index = self.plotdensity_combo.currentIndex()
        diagramtype_index = self.diagramtype_combo.currentIndex()
        saveOnly_checked = self.save_checkbox.isChecked()
        saveOutput_dir = self.output_dir.text()

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

        self.printLog('\nDiagram style: %s' % diagramtype)
        self.printLog('Save file: %s' % saveOnly_checked)
        self.printLog('Input image: %s' % input_file)
        self.printLog('Is Linear?: %s' % colorspace_isLinear)
        self.printLog('No resize?: %s' % dontResize)
        self.printLog('Plotting Density: %s' % plotdensity_index)
        if not dontResize:
            self.printLog('Max Pixel count: %i pixels' % maxPixel)
        self.printLog('Color Space: %s' % colorspace + '\n')

        if saveOnly_checked:
            pltSize = [25, 25]
        else:
            pltSize = [12, 12]

        try:
            prep = cv2.imread(input_file,-1)
            im = Image.open(input_file)
            prepd = prep.dtype
        except:
            self.printLog('Failed to open file, not a valid or unsupported image format')
            self.printLog('\n==---------------------------------==\n')
            return

        if im.info.__contains__('icc_profile') and autoClspc:
            self.printLog('Automatic colorspace detection active')
            stinfo = im.info.get('icc_profile')

            fbuf = io.BytesIO(stinfo)
            prf = ImageCms.ImageCmsProfile(fbuf)

            self.printLog('\nDescription from embedded profile:')
            self.printLog(ImageCms.getProfileDescription(prf))

            infostr = ImageCms.getProfileDescription(prf)

            if '2020' in infostr:
                self.printLog('Colorspace detected: Bt.2020')
                cProfile = 'ITU-R BT.2020'
                trcFunc = 'sRGB'
            elif 'Adobe RGB' in infostr:
                self.printLog('Colorspace detected: Adobe RGB')
                cProfile = 'adobe1998'
                trcFunc = 'Gamma 2.2'
            elif 'Display P3' in infostr:
                self.printLog('Colorspace detected: Display P3')
                cProfile = 'Display P3'
                trcFunc = 'sRGB'
            elif 'DCID65' in infostr:
                self.printLog('Colorspace detected: Display P3')
                cProfile = 'Display P3'
                trcFunc = 'sRGB'
            elif 'ProPhoto' in infostr:
                self.printLog('Colorspace detected: ProPhoto RGB')
                cProfile = 'ProPhoto RGB'
                trcFunc = 'ProPhoto RGB'
            elif 'ACEScg' in infostr:
                self.printLog('Colorspace detected: ACEScg')
                cProfile = 'ACEScg'
                trcFunc = 'sRGB'
            elif 'ACES' in infostr:
                self.printLog('Colorspace detected: ACES')
                cProfile = 'aces'
                trcFunc = 'sRGB'
            elif 'sRGB' in infostr:
                self.printLog('Colorspace detected: sRGB')
                cProfile = 'sRGB'
                trcFunc = 'sRGB'
            else:
                self.printLog('Profile not supported yet, using sRGB instead')
                cProfile = 'sRGB'
                trcFunc = 'sRGB'

            if ('g10' in infostr) or ('Linear' in infostr) :
                self.printLog('Linear TRC detected, switching to linear')
                isLin = True
        else:
            if autoClspc:
                self.printLog('Automatic colorspace detection active')
                self.printLog('No color profile found, using sRGB instead')
                cProfile = 'sRGB'
                trcFunc = 'sRGB'
            else:
                cProfile = colorspace
                trcFunc = 'sRGB'

        im.close()

        np.seterr(divide='ignore', invalid='ignore')
        
        self.printLog("\nImage bitdepth: %s" % prepd)
        self.printLog("width: %s | height: %s" % (prep.shape[1], prep.shape[0]))
       
        imStartSize = prep.shape[0] * prep.shape[1]
        self.printLog("Input pixel count: %i pixels | %.3f MPixels" % (imStartSize, imStartSize / 1000000))

        if (prep.shape[0] * prep.shape[1]) > maxPixel and dontResize == False:

            reduxRatio = np.sqrt((prep.shape[0] * prep.shape[1]) / maxPixel)

            self.printLog("Reduction ratio = 1:%.2f" % reduxRatio)

            prep = cv2.resize(prep, (floor(prep.shape[1] / reduxRatio), floor(prep.shape[0] / reduxRatio)), interpolation=6)
            self.printLog("Resized:")
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

        RGBlin = colour.cctf_decoding(RGB, function=trcFunc)

        ovrSpace = ['sRGB', 'Display P3', 'ITU-R BT.2020', cProfile]

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
                    print('Failed to create a folder to save image')
            else:
                fName = os.path.join(saveOutput_dir, outFileName)
                fiName = fName.replace(os.sep, posixpath.sep)

        self.printLog('\n==---------------------------------==\n')
        sSuccess = False

        #--------Here goes the plotting code--------------
        if diagramtype == 'CIE-1931':

            COL_STYLE = colour.plotting.colour_style()

            if saveOnly_checked:
                COL_STYLE.update(
                    {
                        "grid.alpha": 0.25,
                        "legend.framealpha": 0.25,
                        "legend.loc": 'lower center',
                        "figure.figsize": pltSize,
                        "legend.fontsize": 'xx-large'
                    }
                )
            else:
                COL_STYLE.update(
                    {
                        "grid.alpha": 0.25,
                        "legend.framealpha": 0.25,
                        "legend.loc": 'lower center',
                        "figure.figsize": pltSize,
                    }
                )

            plt.style.use(COL_STYLE)
            plt.style.use("dark_background")

            if saveOnly_checked:
                try:
                    self.printLog('Saving image, please wait...')
                    plot_RGB_chromaticities_in_chromaticity_diagram_CIE1931(
                        RGBlin[...,0:3] if colorspace_isLinear == False else RGB[...,0:3],
                        cProfile,
                        colourspaces=ovrSpace,
                        spectral_locus_colours="RGB",
                        spectral_locus_opacity=0.75,
                        diagram_colours=[0.75, 0.75, 0.75],
                        diagram_opacity=0.15,
                        scatter_kwargs={'s':2, 'alpha':scAlpha},
                        title="CIE 1931 Chromaticity Diagram",
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
                        RGBlin[...,0:3] if colorspace_isLinear == False else RGB[...,0:3],
                        cProfile,
                        colourspaces=ovrSpace,
                        spectral_locus_colours="RGB",
                        spectral_locus_opacity=0.75,
                        diagram_colours=[0.75, 0.75, 0.75],
                        diagram_opacity=0.15,
                        scatter_kwargs={'s':2, 'alpha':scAlpha},
                        title="CIE 1931 Chromaticity Diagram",
                        bounding_box=chRange1931,
                    )
                    self.printLog('Plotting Completed')
                    self.printLog('\n==---------------------------------==\n')
                except:
                    self.printLog('Plotting Failed')
                    self.printLog('\n==---------------------------------==\n')
                    plt.close()
        elif diagramtype == 'CIE-1976-UCS':
            COL_STYLE = colour.plotting.colour_style()
            
            if saveOnly_checked:
                COL_STYLE.update(
                    {
                        "grid.alpha": 0.25,
                        "legend.framealpha": 0.25,
                        "legend.loc": 'lower left',
                        "figure.figsize": pltSize,
                        "legend.fontsize": 'xx-large'
                    }
                )
            else:
                COL_STYLE.update(
                    {
                        "grid.alpha": 0.25,
                        "legend.framealpha": 0.25,
                        "legend.loc": 'lower left',
                        "figure.figsize": pltSize,
                    }
                )

            plt.style.use(COL_STYLE)
            plt.style.use("dark_background")

            if saveOnly_checked:
                try:
                    self.printLog('Saving image, please wait...')
                    plot_RGB_chromaticities_in_chromaticity_diagram_CIE1976UCS(
                        RGBlin[...,0:3] if colorspace_isLinear == False else RGB[...,0:3],
                        cProfile,
                        colourspaces=ovrSpace,
                        spectral_locus_colours="RGB",
                        spectral_locus_opacity=0.75,
                        diagram_colours=[0.75, 0.75, 0.75],
                        diagram_opacity=0.15,
                        scatter_kwargs={'s':2, 'alpha':scAlpha},
                        title="CIE 1976 UCS Chromaticity Diagram",
                        bounding_box=chRange1976,
                        filename=fiName,
                    )
                    plt.close()
                except:
                    sSuccess = False
                    plt.close()
            else:
                try:
                    plot_RGB_chromaticities_in_chromaticity_diagram_CIE1976UCS(
                        RGBlin[...,0:3] if colorspace_isLinear == False else RGB[...,0:3],
                        cProfile,
                        colourspaces=ovrSpace,
                        spectral_locus_colours="RGB",
                        spectral_locus_opacity=0.75,
                        diagram_colours=[0.75, 0.75, 0.75],
                        diagram_opacity=0.15,
                        scatter_kwargs={'s':2, 'alpha':scAlpha},
                        title="CIE 1976 UCS Chromaticity Diagram",
                        bounding_box=chRange1976,
                    )
                    self.printLog('Plotting Completed')
                    self.printLog('\n==---------------------------------==\n')
                except:
                    self.printLog('Plotting Failed')
                    self.printLog('\n==---------------------------------==\n')
                    plt.close()
        else:
            self.printLog('Method invalid')
            self.printLog('\n==---------------------------------==\n')

        if saveOnly_checked:
            if sSuccess:
                self.printLog('Save completed')
                self.printLog(fiName)
            else:
                self.printLog('Save failed, directory invalid or no permission')
            self.printLog('\n==---------------------------------==\n')


    def printLog(self, logtxt):
        self.log_output.appendPlainText(logtxt)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon(os.path.join(basedir, 'gamuticon.ico')))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()