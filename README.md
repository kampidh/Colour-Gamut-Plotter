# Colour-Gamut-Plotter
A simple GUI for [Colour-Science](https://www.colour-science.org/) **plot_RGB_chromaticities_in_chromaticity_diagram** function

Written in **Python 3.9.13**

![Screenshot](Plotter-ss.png)

## Module Dependencies
- colour-science (primary, optional, graphviz, plotting, meshing, freeimage)
- matplotlib (for some reason, it didn't installed from color-science optional)
- pyqt5
- opencv

## Features
- Image file opened with OpenCV instead, so image bit depth is preserved. As colour science read_image is using imageio and downsampled the image to 8 bit.
- Crude automatic colour profile detection using Pillow ImageCMS, parsing embedded color profile data from image and match the string.
- Selectable plotting density. If image is bigger than the plotting density, image is resized with Nearest Neighbour so no interpolation is happening.
- Selectable diagram mode, between CIE 1930 or CIE 1976 UCS Chromaticity diagram.

## Limitation
- Only supports image with RGB model.
- Auto color profile only supports **sRGB, Display P3, Adobe RGB, BT.2020, ProPhoto RGB, ACEScg, and ACES** through string search from image's embedded profile, thus it might not be accurate.
- I haven't been able to extract any curve/matrix/LUT from the embedded color profile, so TRC calculation only applied to each image standards (eg. sRGB TRC for sRGB colourspace).
