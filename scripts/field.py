##############################################################################
#
# Copyright (c) His Majesty the King in Right of Canada, as
# represented by the Minister of Natural Resources, 2023
# 
# Licensed under the MIT license
# (see LICENSE or <http://opensource.org/licenses/MIT>) All files in the 
# project carrying such notice may not be copied, modified, or distributed 
# except according to those terms.
# 
##############################################################################

import re

class Field:
    """
    The class which holds the different names for a given field.

    The types of field names:
    - eod_name: The field name for the eodms_orderdownload (EOD) script,
                specified by the developer (KB)
    - rapi_id: The field ID used in the RAPI (ex: RSAT2.IMAGE_ID)
    - rapi_title: The English title of the field in the RAPI.
    - ui_label: The label of the field used on the EODMS UI.
    - choices: The list of available choices for the field.
    - datatype: The data type of the field.
    - description: The description (or English title) of the field.
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
            * *choices* (``list`` or None) --
              The list of available choices for the field.
            * *datatype* (``str``) --
              The data type of the field.
            * *description* (``str``) --
              The description (or English title) of the field.
        """
        self.eod_name = kwargs.get('eod_name')
        self.rapi_id = kwargs.get('rapi_id')
        self.rapi_title = kwargs.get('rapi_title')
        self.ui_label = kwargs.get('ui_label')
        self.choices = kwargs.get('choices')
        self.datatype = kwargs.get('datatype')
        self.description = kwargs.get('description')

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
    
    def get_choices(self, values_only=False):
        """
        Gets the available choices for the field.

        :return: A list of choices.
        :rtype:  list or None
        """

        # print(f"self.choices: {self.choices}")

        if values_only and self.choices:
            return [c.get('value') for c in self.choices]
        
        return self.choices
    
    def get_datatype(self):
        """
        Gets the data type for the field.

        :return: A list of choices.
        :rtype:  str
        """
        return self.datatype
    
    def get_description(self):
        """
        Gets the description for the field.

        :return: A list of choices.
        :rtype:  str
        """
        return self.description
    
    def verify_choices(self, in_val):
        """
        Verifies a value based on the field's choices.

        :param in_val: The value to check against the choices.
        :type  in_val: str

        :return: Either the proper choice or None.
        :rtype:  str or None
        """

        choices_lw = [c.lower() for c in self.get_choices(True)]
        try:
            idx = choices_lw.index(in_val.lower())
            return self.get_choices(True)[idx]
        except ValueError:
            return None


class CollFields:
    def __init__(self, coll_id):
        self.coll_id = coll_id
        self.fields = []

        # self.add_general_fields()

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
            * *choices* (``list`` or None) --
              The list of available choices for the field.
            * *datatype* (``str``) --
              The data type of the field.
            * *description* (``str``) --
              The description (or English title) of the field.
        """

        # self.fields.append(Field(eod_name=kwargs.get('eod_name'),
        #                          rapi_id=kwargs.get('rapi_id'),
        #                          rapi_title=kwargs.get('rapi_title'),
        #                          ui_label=kwargs.get('ui_label'), 
        #                          choices=kwargs.get('choices')))
        self.fields.append(Field(**kwargs))

    # def add_general_fields(self):
    #     """
    #     Adds a set of fields that are in several collections
    #     """
    #
    #     ord_key_lst = ['COSMO-SkyMed1', 'DMC', 'Gaofen-1', 'GeoEye-1',
    #                    'IKONOS', 'IRS', 'NAPL', 'QuickBird-2', 'PlanetScope',
    #                    'Radarsat1', 'Radarsat2', 'RCMImageProducts',
    #                    'RapidEye', 'SGBAirPhotos', 'SPOT', 'TerraSarX',
    #                    'WorldView-1', 'WorldView-2', 'WorldView-3']
    #
    #     if self.coll_id in ord_key_lst:
    #         self.add_field(eod_name='ORDER_KEY',
    #                        rapi_id='ARCHIVE_IMAGE.ORDER_KEY',
    #                        rapi_title='Order Key',
    #                        ui_label='Order Key')
    #
    #     px_space_lst = ['COSMO-SkyMed1', 'DMC', 'Gaofen-1', 'GeoEye-1',
    #                     'IKONOS', 'IRS', 'QuickBird-2', 'PlanetScope',
    #                     'Radarsat1', 'Radarsat1RawProducts', 'Radarsat2',
    #                     'Radarsat2RawProducts', 'RCMImageProducts',
    #                     'RCMScienceData', 'RapidEye', 'SPOT', 'TerraSarX',
    #                     'WorldView-1', 'WorldView-2', 'WorldView-3']
    #
    #     if self.coll_id in px_space_lst:
    #         self.add_field(eod_name='PIXEL_SPACING',
    #                        rapi_id='SENSOR_BEAM.SPATIAL_RESOLUTION',
    #                        rapi_title='Spatial Resolution',
    #                        ui_label='Pixel Spacing (Metres)')

    def get_eod_fieldnames(self, sort=False, lowered=False):
        """
        Gets the list of EOD fieldnames.
        
        :param sort: Determines whether to sort the list of fieldnames alphabetically.
        :type  sort: boolean
        :param lowered: Determines whether to return the fieldnames in lowercase.
        :type  lowered: boolean

        :return: A list of EOD filenames.
        :rtype: list
        """

        if sort:
            if lowered:
                return sorted([f.get_eod_name().lower() for f in self.fields])
            else:
                return sorted([f.get_eod_name() for f in self.fields])
        else:
            if lowered:
                return [f.get_eod_name().lower() for f in self.fields]
            else:
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
    def __init__(self, eod, rapi):

        self.mapping = {}
        self.rapi = rapi
        self.eod = eod
        self.map_fields()

    def map_fields(self):
        """
        Creates the field mapping for the script.
        """

        collections = self.rapi.get_collections(True)

        self.eod.check_error(collections)

        for coll_id in collections:
            fields = self.rapi.get_available_fields(coll_id) #, ui_fields=True)
            fields = fields['search']

            coll_fields = CollFields(coll_id)
            for key, vals in fields.items():

                if not vals.get('displayed'): continue

                choices = vals.get('choices')
                datatype = vals.get('datatype')
                description = vals.get('description')

                rapi_id = vals['id']
                rapi_title = key
                ui_label = rapi_title

                if rapi_id.find('ORBIT_ABS') > -1:
                    ui_label = 'Orbit Direction' \
                        if coll_id == 'COSMO-SkyMed1' else 'Orbit'
                elif rapi_id.find('Look Direction') > -1:
                    if coll_id == 'ALOS-2':
                        ui_label = 'Orbit Direction'
                elif rapi_id.find('ARCHIVE_FACILITY') > -1:
                    ui_label = 'Archive Facility'
                elif rapi_id.find('BEAM_MNEMONIC') > -1:
                    ui_label = 'Beam Mnemonic'
                elif rapi_id.find('SBEAM') > -1:
                    if coll_id == 'NAPL':
                        ui_label = 'Colour'
                    elif coll_id in [
                        'Radarsat1',
                        'Radarsat1RawProducts',
                        'Radarsat2',
                        'Radarsat2RawProducts',
                        'RCMScienceData',
                    ]:
                        ui_label = 'Beam Mode'
                    elif coll_id == 'RCMImageProducts':
                        ui_label = 'Beam Mode Type'
                    else:
                        ui_label = 'Sensor Mode'
                elif rapi_id.find('CLOUD_PERCENT') > -1:
                    ui_label = 'Maximum Cloud Cover'
                elif rapi_id.find('IMAGE_ID') > -1:
                    ui_label = 'Image Identification'
                elif rapi_id.find('INCIDENCE_ANGLE') > -1:
                    ui_label = 'Incidence Angle (Decimal Degrees)'
                elif rapi_id.find('SENS_INC') > -1:
                    ui_label = 'Incidence Angle (Decimal Degrees)'
                elif rapi_id.find('SPATIAL_RESOLUTION') > -1:
                    ui_label = 'Pixel Spacing (Metres)'
                elif rapi_id.find('RECEPTION_FACILITY') > -1:
                    ui_label = 'Reception Facility'
                elif rapi_id.find('CEOID') > -1:
                    ui_label = 'Value-added Satellite Product Options'

                if ui_label.find('(High)') > -1 or ui_label.find('(Low)') > -1:
                    eod_name = ui_label.replace('(', '').replace(')', '')
                else:
                    eod_name = re.sub("[(\[].*?[)\]]", "", ui_label)
                eod_name = eod_name.strip().upper().replace(' ', '_')

                coll_fields.add_field(eod_name=eod_name, rapi_id=rapi_id,
                                      rapi_title=rapi_title, ui_label=ui_label, 
                                      choices=choices, datatype=datatype, 
                                      description=description)

                if coll_id == 'Radarsat1':
                    for key in ['Radarsat1', 'R1', 'RS1']:
                        self.mapping[key] = coll_fields
                elif coll_id == 'Radarsat2':
                    for key in ['Radarsat2', 'R2', 'RS2']:
                        self.mapping[key] = coll_fields
                elif coll_id == 'RCMImageProducts':
                    for key in ['RCMImageProducts', 'RCM']:
                        self.mapping[key] = coll_fields
                else:
                    self.mapping[coll_id] = coll_fields

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
