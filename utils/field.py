class Field:
    """
    The class which holds the different names for a given field.

    The types of field names:
    - eod_name: The field name for the eodms_orderdownload (EOD) script,
                specified by the developer (KB)
    - rapi_id: The field ID used in the RAPI (ex: RSAT2.IMAGE_ID)
    - rapi_title: The English title of the field in the RAPI.
    - ui_label: The label of the field used on the EODMS UI.
    """

    def __init__(self, **kwargs):
        """
        :param \**kwargs:
        See below

        :Keyword Arguments:
            * *eod_name* (``str``) --
              The field name of the eodms_orderdownload (EOD) script.
            * *rapi_id* (``str``) --
              The field ID in the RAPI.
            * *rapi_title* (``str``) --
              The field name in the RAPI.
            * *ui_label* (``str``) --
              The field name found on the EODMS UI.
        """
        self.eod_name = kwargs.get('eod_name')
        self.rapi_id = kwargs.get('rapi_id')
        self.rapi_title = kwargs.get('rapi_title')
        self.ui_label = kwargs.get('ui_label')

    def get_eod_name(self):
        """
        Gets the EOD script field name.

        :return: The EOD script field name.
        :rtype:  str
        """
        return self.eod_name

    def get_rapi_id(self):
        """
        Gets the RAPI ID field name.

        :return: The RAPI ID field name.
        :rtype: str
        """
        return self.rapi_id

    def get_rapi_title(self):
        """
        Gets the RAPI field title.

        :return: The RAPI field title.
        :rtype:  str
        """
        return self.rapi_title

    def get_ui_label(self):
        """
        Gets the EODMS UI field name.

        :return: The EODMS UI field name.
        :rtype:  str
        """
        return self.ui_label


class CollFields:
    def __init__(self, coll_id):
        self.coll_id = coll_id
        self.fields = []

        self.add_general_fields()

    def add_field(self, **kwargs):
        """
        :param kwargs:
        See below

        :Keyword Arguments:
            * *eod_name* (``str``) --
              The field name of the eodms_orderdownload script.
            * *rapi_id* (``str``) --
              The field ID in the RAPI.
            * *rapi_title* (``str``) --
              The field name in the RAPI.
            * *ui_label* (``str``) --
              The field name found on the EODMS UI.
        """

        self.fields.append(Field(eod_name=kwargs.get('eod_name'),
                                 rapi_id=kwargs.get('rapi_id'),
                                 rapi_title=kwargs.get('rapi_'
                                                       'field_title'),
                                 ui_label=kwargs.get('ui_label')))

    def add_general_fields(self):
        """
        Adds a set of fields that are in several collections
        """

        ord_key_lst = ['COSMO-SkyMed1', 'DMC', 'Gaofen-1', 'GeoEye-1',
                       'IKONOS', 'IRS', 'NAPL', 'QuickBird-2', 'PlanetScope',
                       'Radarsat1', 'Radarsat2', 'RCMImageProducts',
                       'RapidEye', 'SGBAirPhotos', 'SPOT', 'TerraSarX',
                       'WorldView-1', 'WorldView-2', 'WorldView-3']

        if self.coll_id in ord_key_lst:
            self.add_field(eod_name='ORDER_KEY',
                           rapi_id='ARCHIVE_IMAGE.ORDER_KEY',
                           rapi_title='Order Key',
                           ui_label='Order Key')

        px_space_lst = ['COSMO-SkyMed1', 'DMC', 'Gaofen-1', 'GeoEye-1',
                        'IKONOS', 'IRS', 'QuickBird-2', 'PlanetScope',
                        'Radarsat1', 'Radarsat1RawProducts', 'Radarsat2',
                        'Radarsat2RawProducts', 'RCMImageProducts',
                        'RCMScienceData', 'RapidEye', 'SPOT', 'TerraSarX',
                        'WorldView-1', 'WorldView-2', 'WorldView-3']

        if self.coll_id in px_space_lst:
            self.add_field(eod_name='PIXEL_SPACING',
                           rapi_id='SENSOR_BEAM.SPATIAL_RESOLUTION',
                           rapi_title='Spatial Resolution',
                           ui_label='Pixel Spacing (Metres)')

    def get_eod_fieldnames(self):
        """
        Gets the list of EOD fieldnames.

        :return: A list of EOD filenames.
        :rtype: list
        """
        return [f.get_eod_name() for f in self.fields]

    def get_field(self, eod_name):
        """
        Gets a specific field based on the EOD field name.

        :param eod_name: The EOD (this script) field name.
        :type  eod_name: str

        :return: The Field object.
        :rtype:  Field
        """

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
                               rapi_title='Absolute Orbit',
                               ui_label='Orbit Direction')
        self.mapping['COSMO-SkyMed1'] = cosmo_fields

        dmc_fields = CollFields('DMC')
        dmc_fields.add_field(eod_name='CLOUD_COVER',
                             rapi_id='DMC.CLOUD_PERCENT',
                             rapi_title='Cloud Cover',
                             ui_label='Maximum Cloud Cover')
        dmc_fields.add_field(eod_name='INCIDENCE_ANGLE',
                             rapi_id='DMC.INCIDENCE_ANGLE',
                             rapi_title='Sensor Incidence Angle',
                             ui_label='Incidence Angle (Decimal Degrees)')
        self.mapping['DMC'] = dmc_fields

        gao_fields = CollFields('Gaofen-1')
        gao_fields.add_field(eod_name='CLOUD_COVER',
                             rapi_id='SATOPT.CLOUD_PERCENT',
                             rapi_title='Cloud Cover',
                             ui_label='Maximum Cloud Cover')
        gao_fields.add_field(eod_name='INCIDENCE_ANGLE',
                             rapi_id='SATOPT.SENS_INC',
                             rapi_title='Sensor Incidence Angle',
                             ui_label='Incidence Angle (Decimal Degrees)')
        self.mapping['Gaofen-1'] = gao_fields

        geoeye_fields = CollFields('GeoEye-1')
        geoeye_fields.add_field(eod_name='CLOUD_COVER',
                                rapi_id='GE1.CLOUD_PERCENT',
                                rapi_title='Cloud Cover',
                                ui_label='Maximum Cloud Cover')
        geoeye_fields.add_field(eod_name='INCIDENCE_ANGLE',
                                rapi_id='GE1.SENS_INC',
                                rapi_title='Sensor Incidence Angle',
                                ui_label='Incidence Angle (Decimal '
                                         'Degrees)')
        self.mapping['GeoEye-1'] = geoeye_fields

        ikonos_fields = CollFields('IKONOS')
        ikonos_fields.add_field(eod_name='CLOUD_COVER',
                                rapi_id='IKONOS.CLOUD_PERCENT',
                                rapi_title='Cloud Cover',
                                ui_label='Maximum Cloud Cover')
        ikonos_fields.add_field(eod_name='INCIDENCE_ANGLE',
                                rapi_id='IKONOS.SENS_INC',
                                rapi_title='Sensor Incidence Angle',
                                ui_label='Incidence Angle (Decimal '
                                         'Degrees)')
        ikonos_fields.add_field(eod_name='SENSOR_MODE',
                                rapi_id='IKONOS.SBEAM',
                                rapi_title='Sensor Mode',
                                ui_label='Sensor Mode')
        self.mapping['IKONOS'] = ikonos_fields

        irs_fields = CollFields('IRS')
        irs_fields.add_field(eod_name='CLOUD_COVER',
                             rapi_id='IRS.CLOUD_PERCENT',
                             rapi_title='Cloud Cover',
                             ui_label='Maximum Cloud Cover')
        irs_fields.add_field(eod_name='INCIDENCE_ANGLE',
                             rapi_id='IRS.SENS_INC',
                             rapi_title='Sensor Incidence Angle',
                             ui_label='Incidence Angle (Decimal Degrees)')
        irs_fields.add_field(eod_name='SENSOR_MODE',
                             rapi_id='IRS.SBEAM',
                             rapi_title='Sensor Mode',
                             ui_label='Sensor Mode')
        self.mapping['IRS'] = irs_fields

        napl_fields = CollFields('NAPL')
        napl_fields.add_field(eod_name='COLOUR',
                              rapi_id='PHOTO.SBEAM',
                              rapi_title='Sensor Mode',
                              ui_label='Colour')
        napl_fields.add_field(eod_name='SCALE',
                              rapi_id='FLIGHT_SEGMENT.SCALE',
                              rapi_title='Scale',
                              ui_label='Scale'),
        napl_fields.add_field(eod_name='ROLL',
                              rapi_id='ROLL.ROLL_NUMBER',
                              rapi_title='Roll Number',
                              ui_label='Roll'),
        napl_fields.add_field(eod_name='PHOTO_NUMBER',
                              rapi_id='PHOTO.PHOTO_NUMBER',
                              rapi_title='Photo Number',
                              ui_label='Photo Number'),
        napl_fields.add_field(eod_name='PREVIEW_AVAILABLE',
                              rapi_id='PREVIEW_AVAILABLE',
                              rapi_title='Preview Available',
                              ui_label='Preview Available')
        self.mapping['NAPL'] = napl_fields

        plan_fields = CollFields('PlanetScope')
        plan_fields.add_field(eod_name='CLOUD_COVER',
                              rapi_id='SATOPT.CLOUD_PERCENT',
                              rapi_title='Cloud Cover',
                              ui_label='Maximum Cloud Cover')
        plan_fields.add_field(eod_name='INCIDENCE_ANGLE',
                              rapi_id='SATOPT.SENS_INC',
                              rapi_title='Sensor Incidence Angle',
                              ui_label='Incidence Angle (Decimal Degrees)')
        self.mapping['PlanetScope'] = plan_fields

        qb_fields = CollFields('QuickBird-2')
        qb_fields.add_field(eod_name='CLOUD_COVER',
                            rapi_id='QB2.CLOUD_PERCENT',
                            rapi_title='Cloud Cover',
                            ui_label='Maximum Cloud Cover')
        qb_fields.add_field(eod_name='INCIDENCE_ANGLE',
                            rapi_id='QB2.SENS_INC',
                            rapi_title='Sensor Incidence Angle',
                            ui_label='Incidence Angle (Decimal Degrees)')
        qb_fields.add_field(eod_name='SENSOR_MODE',
                            rapi_id='QB2.SBEAM',
                            rapi_title='Sensor Mode',
                            ui_label='Sensor Mode')
        self.mapping['QuickBird-2'] = qb_fields

        r1_fields = CollFields('Radarsat1')
        r1_fields.add_field(eod_name='ORBIT_DIRECTION',
                            rapi_id='RSAT1.ORBIT_DIRECTION',
                            rapi_title='Orbit Direction',
                            ui_label='Orbit Direction')
        r1_fields.add_field(eod_name='INCIDENCE_ANGLE',
                            rapi_id='RSAT1.INCIDENCE_ANGLE',
                            rapi_title='Incidence Angle',
                            ui_label='Incidence Angle (Decimal Degrees)'),
        r1_fields.add_field(eod_name='BEAM_MODE',
                            rapi_id='RSAT1.SBEAM',
                            rapi_title='Sensor Mode',
                            ui_label='Beam Mode'),
        r1_fields.add_field(eod_name='BEAM_MNEMONIC',
                            rapi_id='RSAT1.BEAM_MNEMONIC',
                            rapi_title='Position',
                            ui_label='Beam Mnemonic'),
        r1_fields.add_field(eod_name='ORBIT',
                            rapi_id='RSAT1.ORBIT_ABS',
                            rapi_title='Absolute Orbit',
                            ui_label='Orbit'),
        r1_fields.add_field(eod_name='PRODUCT_TYPE',
                            rapi_id='ARCHIVE_IMAGE.PRODUCT_TYPE',
                            rapi_title='Product Type',
                            ui_label='Product Type'),
        r1_fields.add_field(eod_name='PRODUCT_ID',
                            rapi_id='ARCHIVE_IMAGE.PRODUCT_ID',
                            rapi_title='Product Id',
                            ui_label='Product Id'),
        r1_fields.add_field(eod_name='PROCESSING_LEVEL',
                            rapi_id='PROCESSING_LEVEL_LUT.PROCESSING_LEVEL',
                            rapi_title='Processing Level',
                            ui_label='Processing Level')
        for key in ['Radarsat1', 'R1', 'RS1']:
            self.mapping[key] = r1_fields

        r1raw_fields = CollFields('Radarsat1RawProducts')
        r1raw_fields.add_field(eod_name='ORBIT_DIRECTION',
                               rapi_id='RSAT1.ORBIT_DIRECTION',
                               rapi_title='Orbit Direction',
                               ui_label='Orbit Direction')
        r1raw_fields.add_field(eod_name='INCIDENCE_ANGLE',
                               rapi_id='RSAT1.INCIDENCE_ANGLE',
                               rapi_title='Incidence Angle',
                               ui_label='Incidence Angle (Decimal '
                                        'Degrees)'),
        r1raw_fields.add_field(eod_name='DATASET_ID',
                               rapi_id='RSAT1.DATASET_ID',
                               rapi_title='Dataset Id',
                               ui_label='Dataset Id'),
        r1raw_fields.add_field(eod_name='ARCHIVE_FACILITY',
                               rapi_id='ARCHIVE_CUF.ARCHIVE_FACILITY',
                               rapi_title='Reception Facility',
                               ui_label='Archive Facility'),
        r1raw_fields.add_field(eod_name='RECEPTION_FACILITY',
                               rapi_id='ARCHIVE_CUF.RECEPTION_FACILITY',
                               rapi_title='Reception Facility',
                               ui_label='Reception Facility'),
        r1raw_fields.add_field(eod_name='BEAM_MODE',
                               rapi_id='RSAT1.SBEAM',
                               rapi_title='Sensor Mode',
                               ui_label='Beam Mode'),
        r1raw_fields.add_field(eod_name='BEAM_MNEMONIC',
                               rapi_id='RSAT1.BEAM_MNEMONIC',
                               rapi_title='Position',
                               ui_label='Beam Mnemonic'),
        r1raw_fields.add_field(eod_name='ABSOLUTE_ORBIT',
                               rapi_id='RSAT1.ORBIT_ABS',
                               rapi_title='Absolute Orbit',
                               ui_label='Orbit')
        self.mapping['Radarsat1RawProducts'] = r1raw_fields

        r2_fields = CollFields('Radarsat2')
        r2_fields.add_field(eod_name='ORBIT_DIRECTION',
                            rapi_id='RSAT2.ORBIT_DIRECTION',
                            rapi_title='Orbit Direction',
                            ui_label='Orbit Direction')
        r2_fields.add_field(eod_name='INCIDENCE_ANGLE',
                            rapi_id='RSAT2.INCIDENCE_ANGLE',
                            rapi_title='Incidence Angle',
                            ui_label='Incidence Angle (Decimal Degrees)'),
        r2_fields.add_field(eod_name='SEQUENCE_ID',
                            rapi_id='CATALOG_IMAGE.SEQUENCE_ID',
                            rapi_title='Sequence Id',
                            ui_label='Sequence Id'),
        r2_fields.add_field(eod_name='BEAM_MODE',
                            rapi_id='RSAT2.SBEAM',
                            rapi_title='Sensor Mode',
                            ui_label='Beam Mode'),
        r2_fields.add_field(eod_name='BEAM_MNEMONIC',
                            rapi_id='RSAT2.BEAM_MNEMONIC',
                            rapi_title='Position',
                            ui_label='Beam Mnemonic'),
        r2_fields.add_field(eod_name='LOOK_DIRECTION',
                            rapi_id='RSAT2.ANTENNA_ORIENTATION',
                            rapi_title='Look Direction',
                            ui_label='Look Direction'),
        r2_fields.add_field(eod_name='TRANSMIT_POLARIZATION',
                            rapi_id='RSAT2.TR_POL',
                            rapi_title='Transmit Polarization',
                            ui_label='Transmit Polarization'),
        r2_fields.add_field(eod_name='RECEIVE_POLARIZATION',
                            rapi_id='RSAT2.REC_POL',
                            rapi_title='Receive Polarization',
                            ui_label='Receive Polarization'),
        r2_fields.add_field(eod_name='IMAGE_ID',
                            rapi_id='RSAT2.IMAGE_ID',
                            rapi_title='Image Id',
                            ui_label='Image Identification'),
        r2_fields.add_field(eod_name='RELATIVE_ORBIT',
                            rapi_id='RSAT2.ORBIT_REL',
                            rapi_title='Relative Orbit',
                            ui_label='Relative Orbit')
        for key in ['Radarsat2', 'R2', 'RS2']:
            self.mapping[key] = r2_fields

        r2raw_fields = CollFields('Radarsat2RawProducts')
        r2raw_fields.add_field(eod_name='ORBIT_DIRECTION',
                               rapi_id='RSAT2.ORBIT_DIRECTION',
                               rapi_title='Orbit Direction',
                               ui_label='Orbit Direction')
        r2raw_fields.add_field(eod_name='INCIDENCE_ANGLE',
                               rapi_id='RSAT2.INCIDENCE_ANGLE',
                               rapi_title='Incidence Angle',
                               ui_label='Incidence Angle (Decimal '
                                        'Degrees)'),
        r2raw_fields.add_field(eod_name='LOOK_ORIENTATION',
                               rapi_id='RSAT2.ANTENNA_ORIENTATION',
                               rapi_title='Look Orientation',
                               ui_label='Look Orientation'),
        r2raw_fields.add_field(eod_name='BEAM_MODE',
                               rapi_id='RSAT2.SBEAM',
                               rapi_title='Sensor Mode',
                               ui_label='Beam Mode'),
        r2raw_fields.add_field(eod_name='BEAM_MNEMONIC',
                               rapi_id='RSAT2.BEAM_MNEMONIC',
                               rapi_title='Beam Mnemonic',
                               ui_label='Position'),
        r2raw_fields.add_field(eod_name='TRANSMIT_POLARIZATION',
                               rapi_id='RSAT2.TR_POL',
                               rapi_title='Transmit Polarization',
                               ui_label='Transmit Polarization'),
        r2raw_fields.add_field(eod_name='RECEIVE_POLARIZATION',
                               rapi_id='RSAT2.REC_POL',
                               rapi_title='Receive Polarization',
                               ui_label='Receive Polarization'),
        r2raw_fields.add_field(eod_name='IMAGE_ID',
                               rapi_id='RSAT2.IMAGE_ID',
                               rapi_title='Image Id',
                               ui_label='Image Identification')
        self.mapping['Radarsat2RawProducts'] = r2raw_fields

        rapeye_fields = CollFields('RapidEye')
        rapeye_fields.add_field(eod_name='CLOUD_COVER',
                                rapi_id='RE.CLOUD_PERCENT',
                                rapi_title='Cloud Cover',
                                ui_label='Maximum Cloud Cover')
        rapeye_fields.add_field(eod_name='INCIDENCE_ANGLE',
                                rapi_id='RE.SENS_INC',
                                rapi_title='Sensor Incidence Angle',
                                ui_label='Incidence Angle (Decimal '
                                         'Degrees)')
        rapeye_fields.add_field(eod_name='SENSOR_MODE',
                                rapi_id='RE.SBEAM',
                                rapi_title='Sensor Mode',
                                ui_label='Sensor Mode')
        self.mapping['RapidEye'] = rapeye_fields

        rcm_fields = CollFields('RCMImageProducts')
        rcm_fields.add_field(eod_name='ORBIT_DIRECTION',
                             rapi_id='RCM.ORBIT_DIRECTION',
                             rapi_title='Orbit Direction',
                             ui_label='Orbit Direction'),
        rcm_fields.add_field(eod_name='INCIDENCE_ANGLE',
                             rapi_id='RCM.INCIDENCE_ANGLE',
                             rapi_title='Incidence Angle',
                             ui_label='Incidence Angle (Decimal Degrees)'),
        rcm_fields.add_field(eod_name='BEAM_MNEMONIC',
                             rapi_id='RCM.BEAM_MNEMONIC',
                             rapi_title='Beam Mnemonic',
                             ui_label='Beam Mnemonic'),
        rcm_fields.add_field(eod_name='BEAM_MODE_QUALIFIER',
                             rapi_id='SENSOR_BEAM_CONFIG.BEAM_MODE_QUALIFIER',
                             rapi_title='Beam Mode Qualifier',
                             ui_label='Beam Mode Qualifier'),
        rcm_fields.add_field(eod_name='BEAM_MODE_TYPE',
                             rapi_id='RCM.SBEAM',
                             rapi_title='Beam Mode Type',
                             ui_label='Beam Mode Type'),
        rcm_fields.add_field(eod_name='DOWNLINK_SEGMENT_ID',
                             rapi_id='RCM.DOWNLINK_SEGMENT_ID',
                             rapi_title='Downlink segment ID',
                             ui_label='Downlink segment ID'),
        rcm_fields.add_field(eod_name='LUT_APPLIED',
                             rapi_id='LUTApplied',
                             rapi_title='LUT Applied',
                             ui_label='LUT Applied'),
        rcm_fields.add_field(eod_name='OPEN_DATA',
                             rapi_id='CATALOG_IMAGE.OPEN_DATA',
                             rapi_title='Open Data',
                             ui_label='Open Data'),
        rcm_fields.add_field(eod_name='POLARIZATION',
                             rapi_id='RCM.POLARIZATION',
                             rapi_title='Polarization',
                             ui_label='Polarization'),
        rcm_fields.add_field(eod_name='PRODUCT_FORMAT',
                             rapi_id='PRODUCT_FORMAT.FORMAT_NAME_E',
                             rapi_title='Product Format',
                             ui_label='Product Format'),
        rcm_fields.add_field(eod_name='PRODUCT_TYPE',
                             rapi_id='ARCHIVE_IMAGE.PRODUCT_TYPE',
                             rapi_title='Product Type',
                             ui_label='Product Type'),
        rcm_fields.add_field(eod_name='RELATIVE_ORBIT',
                             rapi_id='RCM.ORBIT_REL',
                             rapi_title='Relative Orbit',
                             ui_label='Relative Orbit'),
        rcm_fields.add_field(eod_name='WITHIN_ORBIT_TUBE',
                             rapi_id='RCM.WITHIN_ORBIT_TUBE',
                             rapi_title='Within Orbital Tube',
                             ui_label='Within Orbital Tube'),
        rcm_fields.add_field(eod_name='SEQUENCE_ID',
                             rapi_id='CATALOG_IMAGE.SEQUENCE_ID',
                             rapi_title='Sequence Id',
                             ui_label='Sequence Id'),
        rcm_fields.add_field(eod_name='SPECIAL_HANDLING_REQUIRED',
                             rapi_id='RCM.SPECIAL_HANDLING_REQUIRED',
                             rapi_title='Special Handling Required',
                             ui_label='Special Handling Required')
        for key in ['RCMImageProducts', 'RCM']:
            self.mapping[key] = rcm_fields

        rcmsci_fields = CollFields('RCMScienceData')
        rcmsci_fields.add_field(eod_name='ORBIT_DIRECTION',
                                rapi_id='RCM.ORBIT_DIRECTION',
                                rapi_title='Orbit Direction',
                                ui_label='Orbit Direction')
        rcmsci_fields.add_field(eod_name='INCIDENCE_ANGLE',
                                rapi_id='RCM.INCIDENCE_ANGLE',
                                rapi_title='Incidence Angle',
                                ui_label='Incidence Angle (Decimal '
                                         'Degrees)'),
        rcmsci_fields.add_field(eod_name='BEAM_MODE',
                                rapi_id='RCM.SBEAM',
                                rapi_title='Beam Mode Type',
                                ui_label='Beam Mode'),
        rcmsci_fields.add_field(eod_name='BEAM_MNEMONIC',
                                rapi_id='RCM.BEAM_MNEMONIC',
                                rapi_title='Beam Mnemonic',
                                ui_label='Beam Mnemonic'),
        rcmsci_fields.add_field(eod_name='TRANSMIT_POLARIZATION',
                                rapi_id='CUF_RCM.TR_POL',
                                rapi_title='Transmit Polarization',
                                ui_label='Transmit Polarization'),
        rcmsci_fields.add_field(eod_name='RECEIVE_POLARIZATION',
                                rapi_id='CUF_RCM.REC_POL',
                                rapi_title='Receive Polarization',
                                ui_label='Receive Polarization'),
        rcmsci_fields.add_field(eod_name='DOWNLINK_SEGMENT_ID',
                                rapi_id='RCM.DOWNLINK_SEGMENT_ID',
                                rapi_title='Downlink Segment ID',
                                ui_label='Downlink Segment ID')
        self.mapping['RCMScienceData'] = rcmsci_fields

        sgb_fields = CollFields('SGBAirPhotos')
        sgb_fields.add_field(eod_name='SCALE',
                             rapi_id='FLIGHT_SEGMENT.SCALE',
                             rapi_title='Scale',
                             ui_label='Scale')
        sgb_fields.add_field(eod_name='ROLL_NUMBER',
                             rapi_id='ROLL.ROLL_NUMBER',
                             rapi_title='Roll Number',
                             ui_label='Roll'),
        sgb_fields.add_field(eod_name='PHOTO_NUMBER',
                             rapi_id='PHOTO.PHOTO_NUMBER',
                             rapi_title='Photo Number',
                             ui_label='Photo Number'),
        sgb_fields.add_field(eod_name='AREA',
                             rapi_id='Area',
                             rapi_title='Area',
                             ui_label='Area')
        self.mapping['SGBAirPhotos'] = sgb_fields

        spot_fields = CollFields('SPOT')
        spot_fields.add_field(eod_name='CLOUD_COVER',
                              rapi_id='SPOT.CLOUD_PERCENT',
                              rapi_title='Cloud Cover',
                              ui_label='Maximum Cloud Cover')
        spot_fields.add_field(eod_name='INCIDENCE_ANGLE',
                              rapi_id='SPOT.SENS_INC',
                              rapi_title='Sensor Incidence Angle',
                              ui_label='Incidence Angle (Decimal Degrees)')
        self.mapping['SPOT'] = spot_fields

        tsar_fields = CollFields('TerraSarX')
        tsar_fields.add_field(eod_name='ORBIT_DIRECTION',
                              rapi_id='TSX1.ORBIT_DIRECTION',
                              rapi_title='Orbit Direction',
                              ui_label='Orbit Direction')
        tsar_fields.add_field(eod_name='INCIDENCE_ANGLE',
                              rapi_id='INCIDENCE_ANGLE',
                              rapi_title='Incidence Angle',
                              ui_label='Incidence Angle (Decimal Degrees)')
        self.mapping['TerraSarX'] = tsar_fields

        vasp_fields = CollFields('VASP')
        vasp_fields.add_field(eod_name='VASP_OPTIONS',
                              rapi_id='CATALOG_SERIES.CEOID',
                              rapi_title='Sequence Id',
                              ui_label='Value-added Satellite Product '
                                       'Options')
        self.mapping['VASP'] = vasp_fields

        wv1_fields = CollFields('WorldView-1')
        wv1_fields.add_field(eod_name='CLOUD_COVER',
                             rapi_id='WV1.CLOUD_PERCENT',
                             rapi_title='Cloud Cover',
                             ui_label='Maximum Cloud Cover')
        wv1_fields.add_field(eod_name='INCIDENCE_ANGLE',
                             rapi_id='WV1.SENS_INC',
                             rapi_title='Sensor Incidence Angle',
                             ui_label='Incidence Angle (Decimal Degrees)')
        wv1_fields.add_field(eod_name='SENSOR_MODE',
                             rapi_id='WV1.SBEAM',
                             rapi_title='Sensor Mode',
                             ui_label='Sensor Mode')
        for key in ['WorldView-1', 'WV1']:
            self.mapping[key] = wv1_fields

        wv2_fields = CollFields('WorldView-2')
        wv2_fields.add_field(eod_name='CLOUD_COVER',
                             rapi_id='WV2.CLOUD_PERCENT',
                             rapi_title='Cloud Cover',
                             ui_label='Maximum Cloud Cover')
        wv2_fields.add_field(eod_name='INCIDENCE_ANGLE',
                             rapi_id='WV2.SENS_INC',
                             rapi_title='Sensor Incidence Angle',
                             ui_label='Incidence Angle (Decimal Degrees)')
        wv2_fields.add_field(eod_name='SENSOR_MODE',
                             rapi_id='WV2.SBEAM',
                             rapi_title='Sensor Mode',
                             ui_label='Sensor Mode')
        for key in ['WorldView-2', 'WV2']:
            self.mapping[key] = wv2_fields

        wv3_fields = CollFields('WorldView-3')
        wv3_fields.add_field(eod_name='CLOUD_COVER',
                             rapi_id='WV3.CLOUD_PERCENT',
                             rapi_title='Cloud Cover',
                             ui_label='Maximum Cloud Cover')
        wv3_fields.add_field(eod_name='INCIDENCE_ANGLE',
                             rapi_id='WV3.SENS_INC',
                             rapi_title='Sensor Incidence Angle',
                             ui_label='Incidence Angle (Decimal Degrees)')
        wv3_fields.add_field(eod_name='SENSOR_MODE',
                             rapi_id='WV3.SBEAM',
                             rapi_title='Sensor Mode',
                             ui_label='Sensor Mode')
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
        """
        Returns a list of collections.

        :return: A list of collections.
        :rtype:  list
        """

        return self.mapping.keys()
