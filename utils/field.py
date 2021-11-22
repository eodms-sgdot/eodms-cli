class Field:
    def __init__(self, **kwargs):
        """
        :param \**kwargs:
        See below

        :Keyword Arguments:
            * *eod_name* (``str``) --
              The field name of the eodms_orderdownload script.
            * *rapi_id* (``str``) --
              The field ID in the RAPI.
            * *rapi_fieldname* (``str``) --
              The field name in the RAPI.
            * *ui_fieldname* (``str``) --
              The field name found on the EODMS UI.
        """
        self.eod_name = kwargs.get('eod_name')
        self.rapi_id = kwargs.get('rapi_id')
        self.rapi_fieldname = kwargs.get('rapi_fieldname')
        self.ui_fieldname = kwargs.get('ui_fieldname')

    def get_eod_name(self):
        return self.eod_name

    def get_rapi_id(self):
        return self.rapi_id

    def get_rapi_fieldname(self):
        return self.rapi_fieldname

    def get_ui_fieldname(self):
        return self.ui_fieldname

class CollFields:
    def __init__(self, coll_id):
        self.coll_id = coll_id
        self.fields = []

        self.add_general_fields()

    def add_field(self, **kwargs):
        """
        :param \**kwargs:
        See below

        :Keyword Arguments:
            * *eod_name* (``str``) --
              The field name of the eodms_orderdownload script.
            * *rapi_id* (``str``) --
              The field ID in the RAPI.
            * *rapi_fieldname* (``str``) --
              The field name in the RAPI.
            * *ui_fieldname* (``str``) --
              The field name found on the EODMS UI.
        """

        self.fields.append(Field(eod_name=kwargs.get('eod_name'),
                                     rapi_id=kwargs.get('rapi_id'),
                                     rapi_fieldname=kwargs.get('rapi_'
                                                               'fieldname'),
                                     ui_fieldname=kwargs.get('ui_fieldname')))

    def add_general_fields(self):
        ord_key_lst = ['COSMO-SkyMed1', 'DMC', 'Gaofen-1', 'GeoEye-1',
                       'IKONOS', 'IRS', 'NAPL', 'QuickBird-2', 'PlanetScope',
                       'Radarsat1', 'Radarsat2', 'RCMImageProducts',
                       'RapidEye', 'SGBAirPhotos', 'SPOT', 'TerraSarX',
                       'WorldView-1', 'WorldView-2', 'WorldView-3']

        if self.coll_id in ord_key_lst:
            self.add_field(eod_name='ORDER_KEY',
                           rapi_id='ARCHIVE_IMAGE.ORDER_KEY',
                           rapi_fieldname='Order Key',
                           ui_fieldname='Order Key')

        px_space_lst = ['COSMO-SkyMed1', 'DMC', 'Gaofen-1', 'GeoEye-1',
                        'IKONOS', 'IRS', 'QuickBird-2', 'PlanetScope',
                        'Radarsat1', 'Radarsat1RawProducts', 'Radarsat2',
                        'Radarsat2RawProducts', 'RCMImageProducts',
                        'RCMScienceData', 'RapidEye', 'SPOT', 'TerraSarX',
                        'WorldView-1', 'WorldView-2', 'WorldView-3']

        if self.coll_id in px_space_lst:
            self.add_field(eod_name='PIXEL_SPACING',
                           rapi_id='SENSOR_BEAM.SPATIAL_RESOLUTION',
                           rapi_fieldname='Spatial Resolution',
                           ui_fieldname='Pixel Spacing (Metres)')

    def get_eod_fieldnames(self):
        """
        Gets the list of EOD fieldnames.

        :return: A list of EOD filenames.
        :rtype: list
        """
        return [f.get_eod_name() for f in self.fields]

    # def get_rapi_fieldname(self, eod_name):
    #
    #     for f in self.fields:
    #         if f.get_eod_name() == eod_name.upper():
    #             return f.get_rapi_fieldname()

    def get_field(self, eod_name):
        for f in self.fields:
            if f.get_eod_name() == eod_name.upper():
                return f

class EodFieldMapper:
    def __init__(self):

        self.mapping = {}
        self.map_fields()

    def map_fields(self):
        """
        Creates the field mapping for the script.
        """

        cosmo_fields = CollFields('COSMO-SkyMed1')
        cosmo_fields.add_field(eod_name='ORBIT_DIRECTION',
                               rapi_id='csmed.ORBIT_ABS',
                               rapi_fieldname='Absolute Orbit',
                               ui_fieldname='Orbit Direction')
        self.mapping['COSMO-SkyMed1'] = cosmo_fields

        dmc_fields = CollFields('DMC')
        dmc_fields.add_field(eod_name='CLOUD_COVER',
                             rapi_id='DMC.CLOUD_PERCENT',
                             rapi_fieldname='Cloud Cover',
                             ui_fieldname='Maximum Cloud Cover')
        dmc_fields.add_field(eod_name='INCIDENCE_ANGLE',
                             rapi_id='DMC.INCIDENCE_ANGLE',
                             rapi_fieldname='Sensor Incidence Angle',
                             ui_fieldname='Incidence Angle (Decimal Degrees)')
        self.mapping['DMC'] = dmc_fields

        gao_fields = CollFields('Gaofen-1')
        gao_fields.add_field(eod_name='CLOUD_COVER',
                             rapi_id='SATOPT.CLOUD_PERCENT',
                             rapi_fieldname='Cloud Cover',
                             ui_fieldname='Maximum Cloud Cover')
        gao_fields.add_field(eod_name='INCIDENCE_ANGLE',
                             rapi_id='SATOPT.SENS_INC',
                             rapi_fieldname='Sensor Incidence Angle',
                             ui_fieldname='Incidence Angle (Decimal Degrees)')
        self.mapping['Gaofen-1'] = gao_fields

        geoeye_fields = CollFields('GeoEye-1')
        geoeye_fields.add_field(eod_name='CLOUD_COVER',
                                rapi_id='GE1.CLOUD_PERCENT',
                                rapi_fieldname='Cloud Cover',
                                ui_fieldname='Maximum Cloud Cover')
        geoeye_fields.add_field(eod_name='INCIDENCE_ANGLE',
                                rapi_id='GE1.SENS_INC',
                                rapi_fieldname='Sensor Incidence Angle',
                                ui_fieldname='Incidence Angle (Decimal '
                                             'Degrees)')
        self.mapping['GeoEye-1'] = geoeye_fields

        ikonos_fields = CollFields('IKONOS')
        ikonos_fields.add_field(eod_name='CLOUD_COVER',
                                rapi_id='IKONOS.CLOUD_PERCENT',
                                rapi_fieldname='Cloud Cover',
                                ui_fieldname='Maximum Cloud Cover')
        ikonos_fields.add_field(eod_name='INCIDENCE_ANGLE',
                                rapi_id='IKONOS.SENS_INC',
                                rapi_fieldname='Sensor Incidence Angle',
                                ui_fieldname='Incidence Angle (Decimal '
                                             'Degrees)')
        ikonos_fields.add_field(eod_name='SENSOR_MODE',
                                rapi_id='IKONOS.SBEAM',
                                rapi_fieldname='Sensor Mode',
                                ui_fieldname='Sensor Mode')
        self.mapping['IKONOS'] = ikonos_fields

        irs_fields = CollFields('IRS')
        irs_fields.add_field(eod_name='CLOUD_COVER',
                             rapi_id='IRS.CLOUD_PERCENT',
                             rapi_fieldname='Cloud Cover',
                             ui_fieldname='Maximum Cloud Cover')
        irs_fields.add_field(eod_name='INCIDENCE_ANGLE',
                             rapi_id='IRS.SENS_INC',
                             rapi_fieldname='Sensor Incidence Angle',
                             ui_fieldname='Incidence Angle (Decimal Degrees)')
        irs_fields.add_field(eod_name='SENSOR_MODE',
                             rapi_id='IRS.SBEAM',
                             rapi_fieldname='Sensor Mode',
                             ui_fieldname='Sensor Mode')
        self.mapping['IRS'] = irs_fields

        napl_fields = CollFields('NAPL')
        napl_fields.add_field(eod_name='COLOUR',
                              rapi_id='PHOTO.SBEAM',
                              rapi_fieldname='Sensor Mode',
                              ui_fieldname='Colour')
        napl_fields.add_field(eod_name='SCALE',
                              rapi_id='FLIGHT_SEGMENT.SCALE',
                              rapi_fieldname='Scale',
                              ui_fieldname='Scale'),
        napl_fields.add_field(eod_name='ROLL',
                              rapi_id='ROLL.ROLL_NUMBER',
                              rapi_fieldname='Roll Number',
                              ui_fieldname='Roll'),
        napl_fields.add_field(eod_name='PHOTO_NUMBER',
                              rapi_id='PHOTO.PHOTO_NUMBER',
                              rapi_fieldname='Photo Number',
                              ui_fieldname='Photo Number'),
        napl_fields.add_field(eod_name='PREVIEW_AVAILABLE',
                              rapi_id='PREVIEW_AVAILABLE',
                              rapi_fieldname='Preview Available',
                              ui_fieldname='Preview Available')
        self.mapping['NAPL'] = napl_fields

        plan_fields = CollFields('PlanetScope')
        plan_fields.add_field(eod_name='CLOUD_COVER',
                              rapi_id='SATOPT.CLOUD_PERCENT',
                              rapi_fieldname='Cloud Cover',
                              ui_fieldname='Maximum Cloud Cover')
        plan_fields.add_field(eod_name='INCIDENCE_ANGLE',
                              rapi_id='SATOPT.SENS_INC',
                              rapi_fieldname='Sensor Incidence Angle',
                              ui_fieldname='Incidence Angle (Decimal Degrees)')
        self.mapping['PlanetScope'] = plan_fields

        qb_fields = CollFields('QuickBird-2')
        qb_fields.add_field(eod_name='CLOUD_COVER',
                            rapi_id='QB2.CLOUD_PERCENT',
                            rapi_fieldname='Cloud Cover',
                            ui_fieldname='Maximum Cloud Cover')
        qb_fields.add_field(eod_name='INCIDENCE_ANGLE',
                            rapi_id='QB2.SENS_INC',
                            rapi_fieldname='Sensor Incidence Angle',
                            ui_fieldname='Incidence Angle (Decimal Degrees)')
        qb_fields.add_field(eod_name='SENSOR_MODE',
                            rapi_id='QB2.SBEAM',
                            rapi_fieldname='Sensor Mode',
                            ui_fieldname='Sensor Mode')
        self.mapping['QuickBird-2'] = qb_fields

        r1_fields = CollFields('Radarsat1')
        r1_fields.add_field(eod_name='ORBIT_DIRECTION',
                            rapi_id='RSAT1.ORBIT_DIRECTION',
                            rapi_fieldname='Orbit Direction',
                            ui_fieldname='Orbit Direction')
        r1_fields.add_field(eod_name='INCIDENCE_ANGLE',
                            rapi_id='RSAT1.INCIDENCE_ANGLE',
                            rapi_fieldname='Incidence Angle',
                            ui_fieldname='Incidence Angle (Decimal Degrees)'),
        r1_fields.add_field(eod_name='BEAM_MODE',
                            rapi_id='RSAT1.SBEAM',
                            rapi_fieldname='Sensor Mode',
                            ui_fieldname='Beam Mode'),
        r1_fields.add_field(eod_name='BEAM_MNEMONIC',
                            rapi_id='RSAT1.BEAM_MNEMONIC',
                            rapi_fieldname='Position',
                            ui_fieldname='Beam Mnemonic'),
        r1_fields.add_field(eod_name='ORBIT',
                            rapi_id='RSAT1.ORBIT_ABS',
                            rapi_fieldname='Absolute Orbit',
                            ui_fieldname='Orbit'),
        r1_fields.add_field(eod_name='PRODUCT_TYPE',
                            rapi_id='ARCHIVE_IMAGE.PRODUCT_TYPE',
                            rapi_fieldname='Product Type',
                            ui_fieldname='Product Type'),
        r1_fields.add_field(eod_name='PRODUCT_ID',
                            rapi_id='ARCHIVE_IMAGE.PRODUCT_ID',
                            rapi_fieldname='Product Id',
                            ui_fieldname='Product Id'),
        r1_fields.add_field(eod_name='PROCESSING_LEVEL',
                            rapi_id='PROCESSING_LEVEL_LUT.PROCESSING_LEVEL',
                            rapi_fieldname='Processing Level',
                            ui_fieldname='Processing Level')
        for key in ['Radarsat1', 'R1', 'RS1']:
            self.mapping[key] = r1_fields

        r1raw_fields = CollFields('Radarsat1RawProducts')
        r1raw_fields.add_field(eod_name='ORBIT_DIRECTION',
                               rapi_id='RSAT1.ORBIT_DIRECTION',
                               rapi_fieldname='Orbit Direction',
                               ui_fieldname='Orbit Direction')
        r1raw_fields.add_field(eod_name='INCIDENCE_ANGLE',
                               rapi_id='RSAT1.INCIDENCE_ANGLE',
                               rapi_fieldname='Incidence Angle',
                               ui_fieldname='Incidence Angle (Decimal '
                                            'Degrees)'),
        r1raw_fields.add_field(eod_name='DATASET_ID',
                               rapi_id='RSAT1.DATASET_ID',
                               rapi_fieldname='Dataset Id',
                               ui_fieldname='Dataset Id'),
        r1raw_fields.add_field(eod_name='ARCHIVE_FACILITY',
                               rapi_id='ARCHIVE_CUF.ARCHIVE_FACILITY',
                               rapi_fieldname='Reception Facility',
                               ui_fieldname='Archive Facility'),
        r1raw_fields.add_field(eod_name='RECEPTION_FACILITY',
                               rapi_id='ARCHIVE_CUF.RECEPTION_FACILITY',
                               rapi_fieldname='Reception Facility',
                               ui_fieldname='Reception Facility'),
        r1raw_fields.add_field(eod_name='BEAM_MODE',
                               rapi_id='RSAT1.SBEAM',
                               rapi_fieldname='Sensor Mode',
                               ui_fieldname='Beam Mode'),
        r1raw_fields.add_field(eod_name='BEAM_MNEMONIC',
                               rapi_id='RSAT1.BEAM_MNEMONIC',
                               rapi_fieldname='Position',
                               ui_fieldname='Beam Mnemonic'),
        r1raw_fields.add_field(eod_name='ABSOLUTE_ORBIT',
                               rapi_id='RSAT1.ORBIT_ABS',
                               rapi_fieldname='Absolute Orbit',
                               ui_fieldname='Orbit')
        self.mapping['Radarsat1RawProducts'] = r1raw_fields

        r2_fields = CollFields('Radarsat2')
        r2_fields.add_field(eod_name='ORBIT_DIRECTION',
                            rapi_id='RSAT2.ORBIT_DIRECTION',
                            rapi_fieldname='Orbit Direction',
                            ui_fieldname='Orbit Direction')
        r2_fields.add_field(eod_name='INCIDENCE_ANGLE',
                            rapi_id='RSAT2.INCIDENCE_ANGLE',
                            rapi_fieldname='Incidence Angle',
                            ui_fieldname='Incidence Angle (Decimal Degrees)'),
        r2_fields.add_field(eod_name='SEQUENCE_ID',
                            rapi_id='CATALOG_IMAGE.SEQUENCE_ID',
                            rapi_fieldname='Sequence Id',
                            ui_fieldname='Sequence Id'),
        r2_fields.add_field(eod_name='BEAM_MODE',
                            rapi_id='RSAT2.SBEAM',
                            rapi_fieldname='Sensor Mode',
                            ui_fieldname='Beam Mode'),
        r2_fields.add_field(eod_name='BEAM_MNEMONIC',
                            rapi_id='RSAT2.BEAM_MNEMONIC',
                            rapi_fieldname='Position',
                            ui_fieldname='Beam Mnemonic'),
        r2_fields.add_field(eod_name='LOOK_DIRECTION',
                            rapi_id='RSAT2.ANTENNA_ORIENTATION',
                            rapi_fieldname='Look Direction',
                            ui_fieldname='Look Direction'),
        r2_fields.add_field(eod_name='TRANSMIT_POLARIZATION',
                            rapi_id='RSAT2.TR_POL',
                            rapi_fieldname='Transmit Polarization',
                            ui_fieldname='Transmit Polarization'),
        r2_fields.add_field(eod_name='RECEIVE_POLARIZATION',
                            rapi_id='RSAT2.REC_POL',
                            rapi_fieldname='Receive Polarization',
                            ui_fieldname='Receive Polarization'),
        r2_fields.add_field(eod_name='IMAGE_ID',
                            rapi_id='RSAT2.IMAGE_ID',
                            rapi_fieldname='Image Id',
                            ui_fieldname='Image Identification'),
        r2_fields.add_field(eod_name='RELATIVE_ORBIT',
                            rapi_id='RSAT2.ORBIT_REL',
                            rapi_fieldname='Relative Orbit',
                            ui_fieldname='Relative Orbit')
        for key in ['Radarsat2', 'R2', 'RS2']:
            self.mapping[key] = r2_fields

        r2raw_fields = CollFields('Radarsat2RawProducts')
        r2raw_fields.add_field(eod_name='ORBIT_DIRECTION',
                               rapi_id='RSAT2.ORBIT_DIRECTION',
                               rapi_fieldname='Orbit Direction',
                               ui_fieldname='Orbit Direction')
        r2raw_fields.add_field(eod_name='INCIDENCE_ANGLE',
                               rapi_id='RSAT2.INCIDENCE_ANGLE',
                               rapi_fieldname='Incidence Angle',
                               ui_fieldname='Incidence Angle (Decimal '
                                            'Degrees)'),
        r2raw_fields.add_field(eod_name='LOOK_ORIENTATION',
                               rapi_id='RSAT2.ANTENNA_ORIENTATION',
                               rapi_fieldname='Look Orientation',
                               ui_fieldname='Look Orientation'),
        r2raw_fields.add_field(eod_name='BEAM_MODE',
                               rapi_id='RSAT2.SBEAM',
                               rapi_fieldname='Sensor Mode',
                               ui_fieldname='Beam Mode'),
        r2raw_fields.add_field(eod_name='BEAM_MNEMONIC',
                               rapi_id='RSAT2.BEAM_MNEMONIC',
                               rapi_fieldname='Beam Mnemonic',
                               ui_fieldname='Position'),
        r2raw_fields.add_field(eod_name='TRANSMIT_POLARIZATION',
                               rapi_id='RSAT2.TR_POL',
                               rapi_fieldname='Transmit Polarization',
                               ui_fieldname='Transmit Polarization'),
        r2raw_fields.add_field(eod_name='RECEIVE_POLARIZATION',
                               rapi_id='RSAT2.REC_POL',
                               rapi_fieldname='Receive Polarization',
                               ui_fieldname='Receive Polarization'),
        r2raw_fields.add_field(eod_name='IMAGE_ID',
                               rapi_id='RSAT2.IMAGE_ID',
                               rapi_fieldname='Image Id',
                               ui_fieldname='Image Identification')
        self.mapping['Radarsat2RawProducts'] = r2raw_fields

        rapeye_fields = CollFields('RapidEye')
        rapeye_fields.add_field(eod_name='CLOUD_COVER',
                                rapi_id='RE.CLOUD_PERCENT',
                                rapi_fieldname='Cloud Cover',
                                ui_fieldname='Maximum Cloud Cover')
        rapeye_fields.add_field(eod_name='INCIDENCE_ANGLE',
                                rapi_id='RE.SENS_INC',
                                rapi_fieldname='Sensor Incidence Angle',
                                ui_fieldname='Incidence Angle (Decimal '
                                             'Degrees)')
        rapeye_fields.add_field(eod_name='SENSOR_MODE',
                                rapi_id='RE.SBEAM',
                                rapi_fieldname='Sensor Mode',
                                ui_fieldname='Sensor Mode')
        self.mapping['RapidEye'] = rapeye_fields

        rcm_fields = CollFields('RCMImageProducts')
        rcm_fields.add_field(eod_name='ORBIT_DIRECTION',
                             rapi_id='RCM.ORBIT_DIRECTION',
                             rapi_fieldname='Orbit Direction',
                             ui_fieldname='Orbit Direction'),
        rcm_fields.add_field(eod_name='INCIDENCE_ANGLE',
                             rapi_id='RCM.INCIDENCE_ANGLE',
                             rapi_fieldname='Incidence Angle',
                             ui_fieldname='Incidence Angle (Decimal Degrees)'),
        rcm_fields.add_field(eod_name='BEAM_MNEMONIC',
                             rapi_id='RCM.BEAM_MNEMONIC',
                             rapi_fieldname='Beam Mnemonic',
                             ui_fieldname='Beam Mnemonic'),
        rcm_fields.add_field(eod_name='BEAM_MODE_QUALIFIER',
                             rapi_id='SENSOR_BEAM_CONFIG.BEAM_MODE_QUALIFIER',
                             rapi_fieldname='Beam Mode Qualifier',
                             ui_fieldname='Beam Mode Qualifier'),
        rcm_fields.add_field(eod_name='BEAM_MODE_TYPE',
                             rapi_id='RCM.SBEAM',
                             rapi_fieldname='Beam Mode Type',
                             ui_fieldname='Beam Mode Type'),
        rcm_fields.add_field(eod_name='DOWNLINK_SEGMENT_ID',
                             rapi_id='RCM.DOWNLINK_SEGMENT_ID',
                             rapi_fieldname='Downlink segment ID',
                             ui_fieldname='Downlink segment ID'),
        rcm_fields.add_field(eod_name='LUT_APPLIED',
                             rapi_id='LUTApplied',
                             rapi_fieldname='LUT Applied',
                             ui_fieldname='LUT Applied'),
        rcm_fields.add_field(eod_name='OPEN_DATA',
                             rapi_id='CATALOG_IMAGE.OPEN_DATA',
                             rapi_fieldname='Open Data',
                             ui_fieldname='Open Data'),
        rcm_fields.add_field(eod_name='POLARIZATION',
                             rapi_id='RCM.POLARIZATION',
                             rapi_fieldname='Polarization',
                             ui_fieldname='Polarization'),
        rcm_fields.add_field(eod_name='PRODUCT_FORMAT',
                             rapi_id='PRODUCT_FORMAT.FORMAT_NAME_E',
                             rapi_fieldname='Product Format',
                             ui_fieldname='Product Format'),
        rcm_fields.add_field(eod_name='PRODUCT_TYPE',
                             rapi_id='ARCHIVE_IMAGE.PRODUCT_TYPE',
                             rapi_fieldname='Product Type',
                             ui_fieldname='Product Type'),
        rcm_fields.add_field(eod_name='RELATIVE_ORBIT',
                             rapi_id='RCM.ORBIT_REL',
                             rapi_fieldname='Relative Orbit',
                             ui_fieldname='Relative Orbit'),
        rcm_fields.add_field(eod_name='WITHIN_ORBIT_TUBE',
                             rapi_id='RCM.WITHIN_ORBIT_TUBE',
                             rapi_fieldname='Within Orbital Tube',
                             ui_fieldname='Within Orbital Tube'),
        rcm_fields.add_field(eod_name='SEQUENCE_ID',
                             rapi_id='CATALOG_IMAGE.SEQUENCE_ID',
                             rapi_fieldname='Sequence Id',
                             ui_fieldname='Sequence Id'),
        rcm_fields.add_field(eod_name='SPECIAL_HANDLING_REQUIRED',
                             rapi_id='RCM.SPECIAL_HANDLING_REQUIRED',
                             rapi_fieldname='Special Handling Required',
                             ui_fieldname='Special Handling Required')
        for key in ['RCMImageProducts', 'RCM']:
            self.mapping[key] = rcm_fields

        rcmsci_fields = CollFields('RCMScienceData')
        rcmsci_fields.add_field(eod_name='ORBIT_DIRECTION',
                                rapi_id='RCM.ORBIT_DIRECTION',
                                rapi_fieldname='Orbit Direction',
                                ui_fieldname='Orbit Direction')
        rcmsci_fields.add_field(eod_name='INCIDENCE_ANGLE',
                                rapi_id='RCM.INCIDENCE_ANGLE',
                                rapi_fieldname='Incidence Angle',
                                ui_fieldname='Incidence Angle (Decimal '
                                             'Degrees)'),
        rcmsci_fields.add_field(eod_name='BEAM_MODE',
                                rapi_id='RCM.SBEAM',
                                rapi_fieldname='Beam Mode Type',
                                ui_fieldname='Beam Mode'),
        rcmsci_fields.add_field(eod_name='BEAM_MNEMONIC',
                                rapi_id='RCM.BEAM_MNEMONIC',
                                rapi_fieldname='Beam Mnemonic',
                                ui_fieldname='Beam Mnemonic'),
        rcmsci_fields.add_field(eod_name='TRANSMIT_POLARIZATION',
                                rapi_id='CUF_RCM.TR_POL',
                                rapi_fieldname='Transmit Polarization',
                                ui_fieldname='Transmit Polarization'),
        rcmsci_fields.add_field(eod_name='RECEIVE_POLARIZATION',
                                rapi_id='CUF_RCM.REC_POL',
                                rapi_fieldname='Receive Polarization',
                                ui_fieldname='Receive Polarization'),
        rcmsci_fields.add_field(eod_name='DOWNLINK_SEGMENT_ID',
                                rapi_id='RCM.DOWNLINK_SEGMENT_ID',
                                rapi_fieldname='Downlink Segment ID',
                                ui_fieldname='Downlink Segment ID')
        self.mapping['RCMScienceData'] = rcmsci_fields

        sgb_fields = CollFields('SGBAirPhotos')
        sgb_fields.add_field(eod_name='SCALE',
                             rapi_id='FLIGHT_SEGMENT.SCALE',
                             rapi_fieldname='Scale',
                             ui_fieldname='Scale')
        sgb_fields.add_field(eod_name='ROLL_NUMBER',
                             rapi_id='ROLL.ROLL_NUMBER',
                             rapi_fieldname='Roll Number',
                             ui_fieldname='Roll'),
        sgb_fields.add_field(eod_name='PHOTO_NUMBER',
                             rapi_id='PHOTO.PHOTO_NUMBER',
                             rapi_fieldname='Photo Number',
                             ui_fieldname='Photo Number'),
        sgb_fields.add_field(eod_name='AREA',
                             rapi_id='Area',
                             rapi_fieldname='Area',
                             ui_fieldname='Area')
        self.mapping['SGBAirPhotos'] = sgb_fields

        spot_fields = CollFields('SPOT')
        spot_fields.add_field(eod_name='CLOUD_COVER',
                              rapi_id='SPOT.CLOUD_PERCENT',
                              rapi_fieldname='Cloud Cover',
                              ui_fieldname='Maximum Cloud Cover')
        spot_fields.add_field(eod_name='INCIDENCE_ANGLE',
                              rapi_id='SPOT.SENS_INC',
                              rapi_fieldname='Sensor Incidence Angle',
                              ui_fieldname='Incidence Angle (Decimal Degrees)')
        self.mapping['SPOT'] = spot_fields

        tsar_fields = CollFields('TerraSarX')
        tsar_fields.add_field(eod_name='ORBIT_DIRECTION',
                              rapi_id='TSX1.ORBIT_DIRECTION',
                              rapi_fieldname='Orbit Direction',
                              ui_fieldname='Orbit Direction')
        tsar_fields.add_field(eod_name='INCIDENCE_ANGLE',
                              rapi_id='INCIDENCE_ANGLE',
                              rapi_fieldname='Incidence Angle',
                              ui_fieldname='Incidence Angle (Decimal Degrees)')
        self.mapping['TerraSarX'] = tsar_fields

        vasp_fields = CollFields('VASP')
        vasp_fields.add_field(eod_name='VASP_OPTIONS',
                              rapi_id='CATALOG_SERIES.CEOID',
                              rapi_fieldname='Sequence Id',
                              ui_fieldname='Value-added Satellite Product '
                                           'Options')
        self.mapping['VASP'] = vasp_fields

        wv1_fields = CollFields('WorldView-1')
        wv1_fields.add_field(eod_name='CLOUD_COVER',
                              rapi_id='WV1.CLOUD_PERCENT',
                              rapi_fieldname='Cloud Cover',
                              ui_fieldname='Maximum Cloud Cover')
        wv1_fields.add_field(eod_name='INCIDENCE_ANGLE',
                              rapi_id='WV1.SENS_INC',
                              rapi_fieldname='Sensor Incidence Angle',
                              ui_fieldname='Incidence Angle (Decimal Degrees)')
        wv1_fields.add_field(eod_name='SENSOR_MODE',
                              rapi_id='WV1.SBEAM',
                              rapi_fieldname='Sensor Mode',
                              ui_fieldname='Sensor Mode')
        for key in ['WorldView-1', 'WV1']:
            self.mapping[key] = wv1_fields

        wv2_fields = CollFields('WorldView-2')
        wv2_fields.add_field(eod_name='CLOUD_COVER',
                             rapi_id='WV2.CLOUD_PERCENT',
                             rapi_fieldname='Cloud Cover',
                             ui_fieldname='Maximum Cloud Cover')
        wv2_fields.add_field(eod_name='INCIDENCE_ANGLE',
                             rapi_id='WV2.SENS_INC',
                             rapi_fieldname='Sensor Incidence Angle',
                             ui_fieldname='Incidence Angle (Decimal Degrees)')
        wv2_fields.add_field(eod_name='SENSOR_MODE',
                             rapi_id='WV2.SBEAM',
                             rapi_fieldname='Sensor Mode',
                             ui_fieldname='Sensor Mode')
        for key in ['WorldView-2', 'WV2']:
            self.mapping[key] = wv2_fields

        wv3_fields = CollFields('WorldView-3')
        wv3_fields.add_field(eod_name='CLOUD_COVER',
                             rapi_id='WV3.CLOUD_PERCENT',
                             rapi_fieldname='Cloud Cover',
                             ui_fieldname='Maximum Cloud Cover')
        wv3_fields.add_field(eod_name='INCIDENCE_ANGLE',
                             rapi_id='WV3.SENS_INC',
                             rapi_fieldname='Sensor Incidence Angle',
                             ui_fieldname='Incidence Angle (Decimal Degrees)')
        wv3_fields.add_field(eod_name='SENSOR_MODE',
                             rapi_id='WV3.SBEAM',
                             rapi_fieldname='Sensor Mode',
                             ui_fieldname='Sensor Mode')
        for key in ['WorldView-3', 'WV3']:
            self.mapping[key] = wv3_fields


    def get_fields(self, coll_id):
        """
        Gets a set of fields based on a Collection ID.

        :param coll_id: The Collection ID.
        :type  coll_id: str

        :return: The mapping of fields for the specified Collection.
        :rtype: list
        """

        return self.mapping[coll_id]

    def get_colls(self):

        return self.mapping.keys()