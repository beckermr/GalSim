# Copyright (c) 2012-2016 by the GalSim developers team on GitHub
# https://github.com/GalSim-developers
#
# This file is part of GalSim: The modular galaxy image simulation toolkit.
# https://github.com/GalSim-developers/GalSim
#
# GalSim is free software: redistribution and use in source and binary forms,
# with or without modification, are permitted provided that the following
# conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions, and the disclaimer given in the accompanying LICENSE
#    file.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions, and the disclaimer given in the documentation
#    and/or other materials provided with the distribution.
"""@file sensor.py

The Sensor classes implement the process of turning a set of photons incident at the surface
of the detector in the focal plane into an image with counts of electrons in each pixel.

The Sensor class itself implements the simplest possible sensor model, which just converts each
photon into an electron in whatever pixel is below the location where the photon hits.
However, it also serves as a base class for other more classes that implement more sophisticated
treatments of the photon to electron conversion and the drift from the conversion layer to the
bottom of the detector.
"""

import numpy as np
import galsim

class Sensor(object):
    """
    The base class for other sensor models, and also an implementation of the simplest possible
    sensor model that just converts each photon into an electron and drops it in the appropriate
    pixel.
    """

    def __init__(self):
        pass

    def accumulate(self, photons, image):
        """Accumulate the photons incident at the surface of the sensor into the appropriate
        pixels in the image.

        Each photon has a position, which corresponds to the (x,y) position at the top of the
        sensor.  In general, they may also have incidence directions and wavelengths, although
        these are not used by the base class implementation.

        The base class implementation simply accumulates the photons above each pixel into that
        pixel.

        @param photons      A PhotonArray instance describing the incident photons
        @param image        The image into which the photons should be accumuated.
        """
        return photons.addTo(image.image)


class SiliconSensor(Sensor):
    """
    A model of a silicon-based CCD sensor that converts photons to electrons at a wavelength-
    dependent depth (probabilistically) and drifts them down to the wells, properly taking
    into account the repulsion of previously accumulated electrons (known as the brighter-fatter
    effect).

    @param config_file      A configuration file from the Poisson simulator with all the details used to generate this sensor model.
    @param vertex_file      A file which contains the distorted pixel coordinates generated by the Poisson simulator.  This file must be paired with config_file.
    @param NumElec          This parameter is the number of electrons in the central pixel in the Poisson simulation that generated the vertex_file.  Depending how the simulation
                            was done, it will depend on different parameters in the config_file, so needs to be entered manually. Note that you can also use this parameter to adjust the strength of the brighter-fatter effect.  For example, if vertex_file was generated with 80,000 electrons in the reference pixel, and you enter 40,000 in NumElec, you will basically be doubling the strength of the brighter-fatter effect.
    @param DiffMult         A parameter used to adjust the amount of diffusion.  Default=1.0 which is the theoretical amount of diffusion.  A value of 0.0 turns off diffusion.
    @param QDist            A parameter which sets how far away pixels are distorted due to charge in a given pixel.  Default=3.  A large value will increase accuracy but take more time. If it is increased larger than 4, the size of the Poisson simulation must be increased to match.
    @param Nrecalc          Sets how often the distorted pixel shapes are recalculated.  Default = every 10,000 photons.
    
    @param rng              A BaseDeviate object to use for the random number generation
                            for the stochastic aspects of the electron production and drift.
                            [default: None, in which case one will be made for you]

    @param photon_file      A file which writes out a list of incoming photons to the sensor.
                            If photon_file = 'None', no file is produced.  Otherwise
                            a file of name photon_file is produced with X,Y locations,
                            dxdz, dydz, and wavelength for each photon ID.

    """
    def __init__(self, config_file, vertex_file, NumElec, rng, DiffMult = 1.0, QDist = 3, Nrecalc = 10000):
        self.photon_file = None
        if rng is None:
            self.rng = galsim.UniformDeviate()
        elif not isinstance(rng, galsim.BaseDeviate):
            raise TypeError("rng is not a BaseDeviate")
        else:
            self.rng = galsim.UniformDeviate(rng)

        cfg_success, ConfigData = self.ReadConfigFile(config_file)
        if cfg_success:
            DiffStep = self.CalcDiffStep(ConfigData['CollectingPhases'], ConfigData['PixelSize'], ConfigData['ChannelStopWidth'], ConfigData['Vbb'], ConfigData['Vparallel_lo'], ConfigData['Vparallel_hi'], ConfigData['CCDTemperature'], DiffMult)
            NumVertices = ConfigData['NumVertices']
            Nx = ConfigData['PixelBoundaryNx']
            Ny = ConfigData['PixelBoundaryNy']
            PixelSize = ConfigData['PixelSize']                        
        else:
            raise IOError("Error reading configuration file %s"%config_file)

        try:
            vertex_data =  np.loadtxt(vertex_file, skiprows = 1)
            #print "NumVertices = %d, NumElec = %d, Nx = %d, Ny = %d, array size = %d"%(NumVertices, NumElec, Nx, Ny, vertex_data.size)
        except IOError:
            print "Vertex file %s not found"%vertex_file

        #try:
        #    abs_data =  np.loadtxt(abs_file, skiprows = 1)
        #    Nabs = abs_data.size()
        #except IOError:
        #    print "Absorption length file %s not found"%abs_file

        if vertex_data.size == 5 * Nx * Ny * (4 * NumVertices + 4):
            self._silicon = galsim._galsim.Silicon(NumVertices, NumElec, Nx, Ny, QDist, Nrecalc, DiffStep, PixelSize, vertex_data)
        else:
            raise IOError("Vertex file %s does not match config file %s"%(vertex_file, config_file))


    def accumulate(self, photons, image):
        """Accumulate the photons incident at the surface of the sensor into the appropriate
        pixels in the image.

        @param photons      A PhotonArray instance describing the incident photons
        @param image        The image into which the photons should be accumuated.
        """

        if self.photon_file is not None:
            self.WritePhotonFile(photons)

        return self._silicon.accumulate(photons, self.rng, image.image)

    def ReadConfigFile(self, filename):
        # This reads the Poisson simulator config file for
        # the settings that were run
        # and returns a dictionary with the values
        ConfigData = {}
        try:
            file = open(filename,'r')
            lines=file.readlines()
            file.close()
        except IOError:
            print "Configuration file %s not found"%filename
            return False, ConfigData 

        try:
            for line in lines:
                ThisLine=line.strip().split()
                ThisLineLength=len(ThisLine)
                if ThisLineLength < 3:
                    continue
                if list(ThisLine[0])[0]=='#' or ThisLine[0]=='\n':
                    continue
                try:
                    ParamName = ThisLine[0]
                    ThisLine.remove(ThisLine[0])
                    for counter,item in enumerate(ThisLine):
                        if list(item)[0] == '#':
                            del ThisLine[counter:] # Strip the rest of the line as a comment
                            continue
                        if item == '=':
                            ThisLine.remove(item)
                            continue
                    if len(ThisLine) == 0:
                        continue
                    elif len(ThisLine) == 1:
                        ThisParam = ThisLine[0]
                        try: ConfigData[ParamName] = int(ThisParam)
                        except ValueError:
                            try:
                                ConfigData[ParamName] = float(ThisParam)
                            except ValueError:
                                try:
                                    ConfigData[ParamName] = ThisParam
                                except ValueError:
                                    return False, ConfigData 
                    else:
                        ThisParam = []
                        for item in ThisLine:
                            try: ThisParam.append(int(item))
                            except ValueError:
                                try: ThisParam.append(float(item))
                                except ValueError:
                                    ThisParam.append(item)
                        ConfigData[ParamName] = ThisParam
                except (IOError, ValueError):
                    continue
        except Exception as e:
            print "Error reading configuration file %s. Exception of type %s and args = \n"%(filename,type(e).__name__), e.args 
            return False, ConfigData 

        return True, ConfigData

    def CalcDiffStep(self, CollectingPhases, PixelSize, ChannelStopWidth, Vbb, Vparallel_lo, Vparallel_hi, CCDTemperature, DiffMult):
        # This calculates the diffusion step size given the detector
        # parameters.  The diffusion step size is the mean radius of diffusion
        # assuming the electron propagates the full width of the sensor.
        # It depends on the temperature, the sensor voltages, and
        # the DiffMult parameter.
                    
        # Set up the collection area and the diffusion step size at 100 C
        collXmin = ChannelStopWidth / (2.0 * PixelSize)
        collXwidth = (PixelSize - ChannelStopWidth) / PixelSize
        if CollectingPhases == 1:
            # This is one collecting gate
            collYmin = 1.0 / 3.0
            collYwidth = 1.0 / 3.0
            Vdiff = (2.0 * Vparallel_lo + Vparallel_hi) / 3.0 - Vbb
        elif CollectingPhases == 2:
            #This is two collecting gates
            collYmin = 1.0 / 6.0
            collYwidth = 2.0 / 3.0
            Vdiff = (Vparallel_lo + 2.0 * Vparallel_hi) / 3.0 - Vbb
        else:
            print "Error calculating DiffStep.  Diffusion turned off."
            return 0.0;
        DiffStep = 100.0 * np.sqrt(2.0 * 0.026 * CCDTemperature / 298.0 / Vdiff) * DiffMult
        # 100.0 is the detector thickness in microns.
        # .026 is kT/q at room temp (298 K)
        return DiffStep

    def WritePhotonFile(self, photons):
        # This writes out a list of the incoming photons.
        file = open(self.photon_file, 'w')
        file.write('ID \t X(pixels) \t Y(pixels) \t dxdz      \t dydz      \t lambda(nm)\n')
        for i in range(photons.size()):
            x0 = photons.getX(i) # in pixels
            y0 = photons.getY(i) #in pixels
            if photons.hasAllocatedWavelengths():
                lamb = photons.getWavelength(i) # in nm
            else:
                lamb = 0.0

            if photons.hasAllocatedAngles():
                dxdz = photons.getDXDZ(i)
                dydz = photons.getDYDZ(i)
            else:
                dxdz = 0.0
                dydz = 0.0
            file.write('%d \t %.6f \t %.6f \t %.6f \t %.6f \t %.6f\n'%(i,x0,y0,dxdz,dydz,lamb))
        file.close()
        return
