import json
import logging
import urllib.request

CONSTANTS = {
            "output_formats": [
                {"id": 1, "label": "GeoTIFF", "active": True, "display_order": 1, "default": True, "extension": "tif"},
                {"id": 2, "label": "PNG", "active": False, "display_order": 4, "default": False, "extension": "png"},
                {"id": 3, "label": "BMP", "active": False, "display_order": 3, "default": False, "extension": "bmp"},
                {"id": 4, "label": "ENVI (hdr)", "active": False, "display_order": 2, "default": False, "extension": "bil"},
                {"id": 5, "label": "XML", "active": False, "display_order": 999, "default": False, "extension": "xml"}
            ],
            "dem_resamplings": [
                {"id": 1, "label": "Nearest Neighbour", "active": True, "display_order": 1, "default": False},
                {"id": 2, "label": "Bilinear Interpolation", "active": True, "display_order": 2, "default": True},
                {"id": 3, "label": "Cubic Convolution", "active": True, "display_order": 3, "default": False},
                {"id": 4, "label": "Bi-Sinc Interpolation", "active": True, "display_order": 4, "default": False},
                {"id": 5, "label": "Bi-Cubic Interpolation", "active": True, "display_order": 5, "default": False}
            ],
            "resampling_methods": [
                {"id": 1, "label": "Nearest Neighbour", "active": True, "display_order": 1, "default": False, "gamma_code": "0"},
                {"id": 2, "label": "Bi-cubic", "active": True, "display_order": 3, "default": True, "gamma_code": "1"},
                {"id": 3, "label": "Bi-linear", "active": True, "display_order": 2, "default": False, "gamma_code": "3"},
                {"id": 4, "label": "Bi-cubic of log", "active": False, "display_order": 999, "default": False, "gamma_code": "2"},
            ],
            "dems": [
                {"id": 1, "label": "CDEM", "active": True, "display_order": 1},
                {"id": 2, "label": "CDSM (CDEM+SRTM)", "active": True, "display_order": 2},
                {"id": 3, "label": "SRTM 30m (Canada)", "active": True, "display_order": 3},
                {"id": 4, "label": "SRTM 90m (World)", "active": True, "display_order": 4},
                {"id": 5, "label": "Fixed Elevation - 0 meter at Mean Sea Level", "active": False, "display_order": 5},
                {"id": 6, "label": "ASTER 30m (World)", "active": True, "display_order": 6},
                {"id": 7, "label": "SRTM 30m (World)", "active": True, "display_order": 5},
                {"id": 8, "label": "EQUI7 Basemap (NA)", "active": False, "display_order": 8}
            ],
            "projections": [
                {"id": 1, "label": "UTM (auto) / NAD83  (CSRS)", "active": True, "display_order": 1},
                {"id": 2, "label": "UTM (auto) / WGS84", "active": True, "display_order": 2},
                {"id": 3, "label": "UTM (auto) / NAD27", "active": False, "display_order": 3},
                {"id": 4, "label": "UTM / NAD83 (CSRS)", "active": True, "display_order": 4},
                {"id": 5, "label": "UTM / WGS84", "active": True, "display_order": 5},
                {"id": 6, "label": "UTM / NAD27", "active": False, "display_order": 6},
                {"id": 7, "label": "Geographic / WGS84", "active": False, "display_order": 7},
                {"id": 9, "label": "Canada Atlas Lambert / NAD83 (EPSG:3978)", "active": True, "display_order": 10},
                {"id": 11, "label": "Canada Albers Equal Area / NAD83 (EPSG:102001)", "active": True, "display_order": 13},
                {"id": 12, "label": "Polar Stereographic - North / WGS84", "active": False, "display_order": 16},
                {"id": 13, "label": "Polar Stereographic - South / WGS84", "active": False, "display_order": 17},
                {"id": 14, "label": "Geographic / NAD83 (CSRS)", "active": False, "display_order": 8},
                {"id": 15, "label": "Geographic / NAD27", "active": False, "display_order": 9},
                {"id": 16, "label": "Canada Crop Inventory Albers Equal Area / WGS84 ", "active": True, "display_order": 14},
                {"id": 17, "label": "NSIDC Sea Ice Polar Stereographic North / WGS84", "active": True, "display_order": 15},
                {"id": 18, "label": "NSIDC EASE-Grid 2.0 North / WGS84", "active": True, "display_order": 16},
                {"id": 19, "label": "Canada Atlas Lambert / NAD83 (CSRS) (EPSG:3979)", "active": False, "display_order": 11}
            ],
            "ortho_methods": [
                {"id": 1, "label": "Rational Function", "active": True, "display_order": 1},
                {"id": 2, "label": "Range Doppler", "active": False, "display_order": 2}
            ],
            "mosaic_overlap_modes": [
                {"id": 1, "label": "Average valid inputs", "active": False, "display_order": 3, "default": False},
                {"id": 2, "label": "First image preferred", "active": False, "display_order": 2, "default": False},
                {"id": 3, "label": "Last image preferred", "active": True, "display_order": 1, "default": True}
            ],
            "weighting_types": [
                {"id": 0, "label": "Constant", "active": True, "display_order": 1, "default": True},
                {"id": 1, "label": "Linear", "active": True, "display_order": 2, "default": False},
                {"id": 2, "label": "Gaussian", "active": True, "display_order": 3, "default": False}
            ],
            "angle_units": [
                {'id': 1, 'label': 'Degree', 'active': True, 'display_order': 1, 'default': True},
                {'id': 2, 'label': 'Radian', 'active': True, 'display_order': 2, 'default': False}
            ],
            "gd_spat_avgs": [
                {'id': 1, 'label': 'x1', 'active': True, 'display_order': 1, 'default': False, 'multilooking_value': 1},
                {'id': 2, 'label': 'x2', 'active': True, 'display_order': 2, 'default': False, 'multilooking_value': 2},
                {'id': 3, 'label': 'x4', 'active': True, 'display_order': 3, 'default': True, 'multilooking_value': 4},
                {'id': 4, 'label': 'x8', 'active': True, 'display_order': 4, 'default': False, 'multilooking_value': 8}
            ],
            "vlg_spat_avgs": [
                {'id': 1, 'label': 'x8', 'active': True, 'display_order': 1, 'default': False, 'multilooking_value': 8},
                {'id': 2, 'label': 'x16 (recommended)', 'active': True, 'display_order': 2, 'default': True, 'multilooking_value': 16},
                {'id': 3, 'label': 'x32', 'active': True, 'display_order': 3, 'default': False, 'multilooking_value': 32},
                {'id': 4, 'label': 'x64', 'active': True, 'display_order': 4, 'default': False, 'multilooking_value': 64}             
            ],
            "polarizations": [
                {'id': 1, 'label': 'All available', 'uid_name': 'AllPol', 'active': True, 'display_order': 1, 'default': True},
                {'id': 2, 'label': 'CH', 'uid_name': 'CHPol', 'active': True, 'display_order': 2, 'default': False},
                {'id': 3, 'label': 'CV', 'uid_name': 'CVPol', 'active': True, 'display_order': 3, 'default': False},
                {'id': 4, 'label': 'HH', 'uid_name': 'HHPol', 'active': True, 'display_order': 4, 'default': False},
                {'id': 5, 'label': 'HV', 'uid_name': 'HVPol', 'active': True, 'display_order': 5, 'default': False},
                {'id': 6, 'label': 'VV', 'uid_name': 'VVPol', 'active': True, 'display_order': 6, 'default': False},
                {'id': 7, 'label': 'VH', 'uid_name': 'VHPol', 'active': True, 'display_order': 7, 'default': False}
            ],
            "units": [
                {'id': 1, 'label': 'Meters', 'active': True, 'display_order': 1, 'default': True},
                {'id': 2, 'label': 'Degrees', 'active': True, 'display_order': 2, 'default': False}
            ]
        }

def create_table_row(row, col_lens, centre=False):
    """
    Creates a table row.

    :param row: The row information to add.
    :type  row: dict
    :param col_lens: The lengths of the columns for the row.
    :type  col_lens: list
    :param centre: Determines whether to centre the text within the colum. 
                    Otherwise the text is left justified.
    :type  centre: bool

    :return: The row for Markdown.
    :rtype:  str
    """

    row_str = "|"
    for idx, val in enumerate(row):
        col_len = col_lens[idx]
        if centre:
            row_str += " " + str(val).center(col_len) + " |"
        else:
            row_str += " " + str(val).ljust(col_len) + " |"

    row_str += "\n"

    return row_str

def create_divider(col_lens):
    """
    Creates the divider for the table between the headings and rows.

    :param col_lens: The column lengths.
    :type  col_lens: list

    :return: The divider for Markdown.
    :rtype:  str
    """

    row_str = "|"
    for count in col_lens:
        row_str += "-" + '-'*count + "-|"

    row_str += "\n"

    return row_str

def create_table(title, rows):
    """
    Creates a Markdown table for logging purposes.

    :param title: The title of the table.
    :type  title: str
    :param rows: The set of rows for the table.
    :type  rows: list
    """

    # Get length of column
    keys = list(rows[0].keys())

    col_lengths = []
    for k in keys:
        col_lengths.append([len(k)])

    for r in rows:
        for c_idx, v in enumerate(r.values()):
            lengths = col_lengths[c_idx]
            lengths.append(len(str(v)))
            col_lengths[c_idx] = lengths

    cols_lens = [max(c) for c in col_lengths]

    # print(f"cols_lens: {cols_lens}")

    total_lens = sum([c + 3 for c in cols_lens])
    title_str = title.center(total_lens-1)

    table_text = f"|{title_str}|\n"
    table_text += "|" + "-"*(total_lens-1) + "|\n"
    table_text += create_table_row(keys, cols_lens, True)

    table_text += create_divider(cols_lens)

    for r in rows:
        table_text += create_table_row(r.values(), cols_lens)

    return table_text

class Product:

    def __init__(self, product_info):
        self.id = product_info.get('product_id')
        self.name = product_info.get('name')
        self.display_order = product_info.get('display_order')

    def as_dict(self):
        """
        Returns the Product information as a dictionary.

        :return: The Product information.
        :rtype:  dict
        """

        return {
            "id": self.id,
            "name": self.name,
            "display_order": self.display_order
        }
    
    def get_id(self):
        """
        Gets the Id of the Product.

        :return: The Product Id.
        :rtype:  str
        """

        return self.id
    
    def get_name(self):
        """
        Gets the name of the Product.

        :return: The Product name.
        :rtype:  str
        """

        return self.name

class Parameter:

    def __init__(self, param_info, multiple=False):
        self.param_id = param_info.get('param_id')
        self.label = param_info.get('label')
        self.data_type = param_info.get('data_type')
        self.default = param_info.get('default')
        self.display_order = param_info.get('display_order')
        self.constants_key = param_info.get('constants_key')
        in_subs = param_info.get('sub_params')
        self.multiple = multiple

        # print(f"\nParameter Values:")
        # print(f"  Parameter Id: {self.param_id}")
        # print(f"  Label: {self.label}")
        # print(f"  Date Type: {self.data_type}")
        # print(f"  Default: {self.default}")
        # print(f"  Display Order: {self.display_order}")
        # print(f"  Constants Key: {self.constants_key}")
        # print(f"  Multiple Values: {self.multiple}")

        # # self.display_order = display_order
        # self.sub_args = []
        # s_args = kwargs.get('sub_arg')
        # if not isinstance(s_args, list) and s_args:
        #     self.sub_args = [s_args]
        # else:
        #     self.sub_args = s_args
        # self.constants = kwargs.get('constants')
        # self.default = kwargs.get('default')
        # self.multiple = kwargs.get('multiple')
        # self.required = kwargs.get('required')
        # self.ignore = True if kwargs.get('ignore') else False

        # if self.data_type == bool:
        #     self.default = False

        self.sub_params = None
        if in_subs:
            self.sub_params = list()
            for param in in_subs:
                self.sub_params.append(Parameter(param))

        # print(f"self.param_id: {self.param_id}")
        # print(f"self.constants_key: {self.constants_key}")
        self.const_vals = CONSTANTS.get(self.constants_key)
        # print(f"self.const_vals: {self.const_vals}")

        if self.const_vals and not self.default:
            for c in self.const_vals:
                if c.get('default'):
                    self.default = str(c.get('id'))
                else:
                    self.default = "1"

        self.value = None
        if self.default:
            if self.const_vals:
                # print(f"self.default: {self.default}")
                available_vals = [c for c in self.const_vals 
                                   if c.get('id') == int(self.default)]
                if len(available_vals) > 0:
                    self.value = available_vals[0].get('id')
            else:
                self.value = self.default

        # print(f"self.const_vals 2: {self.const_vals}")

    def get_data_type(self):
        """
        Gets the data type of the parameter.

        :return: The data type of the parameter.
        :rtype:  str
        """

        return self.data_type

    def get_default_idx(self):
        """
        Gets the index of the default value in the constant values for the 
        Parameter.

        :return: The index of the default from the constants list.
        :rtype:  int
        """

        for idx, c in enumerate(self.const_vals):
            if c.get('label') == self.default:
                return idx + 1

    def get_default(self, **kwargs):
        """
        Gets the default value of the parameter from the constants dict.

        :param **kwargs:
        Options include:
            **as_value**: Returns the label of the default value.
            **as_listidx**: Returns the list index of the default value.
            **as_id**: Returns the Id of the default value.
        :type  **kwargs: dict
        """

        as_value = kwargs.get('as_value')
        as_listidx = kwargs.get('as_listidx')
        as_id = kwargs.get('as_id')
        include_label = kwargs.get('include_label')

        if not self.const_vals:
            return self.default

        if as_value or as_id:
            for c in self.const_vals:
                if str(c.get('id')) == str(self.default):
                    if as_value:
                        return c.get('label')
                    elif as_id:
                        if include_label:
                            return f"{c.get('id')} - {c.get('label')}"
                        else:
                            return c.get('id')
        elif as_listidx:
            active_constants = [c for c in self.const_vals if c.get('active')]
            for idx, c in enumerate(active_constants):
                if str(c.get('id')) == str(self.default):
                    if include_label:
                        return f"{idx + 1} - {c.get('label')}"
                    else:
                        return idx + 1

    def get_label(self):
        """
        Gets the label of the Parameter.

        :return: The Parameter label.
        :rtype:  str
        """

        return self.label
    
    def get_value(self, as_label=False, with_idx=False):
        """
        Gets various options (see below for more returns) for the Parameter 
        value.

        :param as_label: Determines whether to return the Parameter value (or 
                        "on" and "off" for "bool" data type).
        :type  as_label: bool
        :param with_idx: Determines whether to include the constant Id along
                        with the Parameter value when getting a constant.
        :type  with_idx: bool
        
        :return: The value returned depends on:
                - If Parameter data type is "bool" and as_label is False, return 
                    the Parameter value.
                - If Parameter data type is "bool", as_label is True and 
                    the Parameter value is set, return "on".
                - If Parameter data type is "bool, as_label is True and 
                    the Parameter value is None, return "off".
                - If self.const_vals is set, as_label is True and with_idx is
                    True, return the Id (index) of the constant along with the 
                    Parameter value.
                - If self.const_vals is set, as_label is True and with_idx is
                    False, return the Parameter value.
                - If self.const_vals is set, as_label and with_idx are both 
                    False, return the Id (index) of the constant.
                - If none of the above, return the Parameter value.
        :rtype:  str
        """

        out_value = str(self.value)
        if self.data_type == 'float':
            out_value = '{:f}'.format(float(self.value))

        if self.data_type == "bool":
            if not as_label:
                return out_value
            if self.value:
                return "on"
            return "off"
        
        # print(f"self.constants: {self.constants}")
        if self.const_vals:
            ids = [c.get('id') for c in self.const_vals 
                    if c.get('label') == self.value]
            # print(f"ids: {ids}")
            if len(ids) > 0:
                id_val = str(ids[0])
                if as_label:
                    if with_idx:
                        return f"{id_val} - {out_value}"
                    return out_value
                # print(f"id_val: {id_val}")
                return id_val
            
        return out_value
    
    def get_sub_param(self, param_id=None):
        """
        Gets a single or list of sub parameters.

        :param param_id: The parameter Id of the single parameter to return.
                        If None, a list of sub parameters is returned.
        :type  param_id: str

        :return: A single sub parameters or a list.
        :rtype:  sar.Parameter or list[sar.Parameter]
        """

        if param_id:
            for s_param in self.sub_params:
                if param_id == s_param.param_id:
                    return s_param
        return self.sub_params
    
    def set_value(self, val):
        """
        Sets the Parameter value.

        :param val: The value to add to the Parameter.
        :type  val: str or list[str] if Parameter allows multiple.
        """

        if isinstance(val, list) and not self.multiple:
            val = val[0]

        # Verify entry
        try:
            eval(f"{self.data_type}(val)")
        except ValueError:
            return False

        self.value = val

        return True

class Method:

    def __init__(self, method_id, name, params, products=None):
        self.id = method_id
        self.name = name
        self.params = params
        self.products = products

        self.param_runs = list()
        self.prod_runs = list()

    def get_id(self):
        """
        Gets the Method Id.

        :return: The Method Id.
        :rtype:  int
        """

        return self.id

    def get_parameter(self, param_id):
        """
        Gets a specific Parameter from the list of runs.

        :param param_id: The Parameter param_id
        :type  param_id: str

        :return: The Parameter with the param_id.
        :rtype:  sar.Parameter
        """

        for param in self.param_runs:
            if param.param_id == param_id:
                return param

    def get_parameters(self):
        """
        Gets the list of Parameters for the this Method.

        :return: A list of Parameters
        :rtypr:  list[sar.Parameters]
        """

        return self.params

    def get_product_by_id(self, prod_id):
        """
        Gets a Product based on its Id.

        :param prod_id: The Product Id.
        :type  prod_id: str

        :return: The Product based on the Product Id.
        :rtype:  sar.Product
        """

        for p in self.products:
            if p.id == prod_id:
                return p
    
    def get_products(self, display_order=True):
        """
        Gets a list of Products for the Method.

        :param display_order: Determines whether to sort the list of Products
                            by their display_order.
        :type  display_order: bool

        :return: A list of Products.
        :rtype:  list[sar.Products]
        """

        if not display_order:
            return self.products

        if self.products:
            dict_lst = [p.as_dict() for p in self.products]
            # print(f"dict_lst: {dict_lst}")
            ordered_dicts = sorted(dict_lst, key=lambda d: d['display_order'])
            return [self.get_product_by_id(d.get('id')) for d in ordered_dicts]
    
    def add_param_run(self, param):
        """
        Adds a Parameter for running.

        :param param: The Parameter to add.
        :type  param: sar.Parameter
        """

        self.param_runs.append(param)

    def add_prod_run(self, prod):
        """
        Adds a Product for running.

        :param prod: The Product to add.
        :type  prod: sar.Product
        """

        self.prod_runs.append(prod)

    def get_param_runs(self):
        """
        Gets a list of Parameters which will be run through the SAR Toolbox.

        :return: A list of Parameters.
        :rtype:  list[sar.Parameter]
        """

        return self.param_runs

    def get_prod_runs(self):
        """
        Gets a list of Products which will be run through the SAR Toolbox.

        :return: A list of Products.
        :rtype:  list[sar.Products]
        """

        return self.prod_runs

    def set_param_runs(self, indices):
        """
        Sets the list of Parameters which will be run through the SAR Toolbox.

        :param indices: A list of indices based on the available Parameters 
                        (self.param_runs).
        :type  indices: list[int]

        :return: The list of Parameters which will be run.
        :rtype:  list[sar.Parameter]
        """

        self.param_runs = [self.params[int(i) - 1] for i in indices]
        return self.param_runs

    def set_prod_runs(self, in_prods):
        """
        Sets the list of Products which will be run through the SAR Toolbox.

        :param in_prods: A list of Products or a list of indices.
        :type  in_prods: list[sar.Products] or list[int]

        :return: The list of Products which will be run.
        :rtype:  list[sar.Products]
        """
        
        if isinstance(in_prods[0], int):
            self.prod_runs = [self.products[int(i) - 1] for i in in_prods]
        else:
            self.prod_runs = in_prods
        return self.prod_runs

    def print_info(self):
        """
        Prints the information of the Method such as Parameters and Products.
        """

        title = f'"{self.name}" Method Parameters'
        rows = [{"Parameter": f"{param.label}:", "Value": 
                 f'"{param.get_value(True, True)}"'} 
                 for param in self.param_runs]
        
        if self.prod_runs:
            prod_rows = [{"Parameter": f"{prod.name}:", "Value": f'"True"'} 
                         for prod in self.prod_runs]

            rows = rows + prod_rows

        print()
        print(create_table(title, rows))

class Category:

    def __init__(self, cat_id, name, methods):
        self.id = cat_id
        self.name = name
        self.methods = methods
        self.method_runs = list()

    def get_id(self):
        """
        Gets the Id of the Category.

        :return: The Category Id.
        :rtype:  int
        """

        return self.id
    
    def get_name(self):
        """
        Gets the Category name.

        :return: The Category name.
        :rtype:  str
        """

        return self.name

    def get_methods(self):
        """
        Gets a list of available Methods for the Category.

        :return: A list of available Methods.
        :rtype:  list[sar.Method]
        """

        return self.methods
    
    def get_method_names(self, with_ids=False):
        """
        Gets a list of available Method names for the Category.

        :return: A list of available Method names.
        :rtype:  list[str]
        """

        if with_ids:
            return [f"{m.name} ({m.id})" for m in self.get_methods()]

        return [m.name for m in self.get_methods()]

    def get_method_runs(self):
        """
        Gets a list of the Methods which will be run through the SAR Toolbox.

        :return: A list of Methods for running.
        :rtype:  list[sar.Method]
        """

        return self.run_methods

    def set_method_runs(self, indices):
        """
        Sets the Methods which will be run through the SAR Toolbox.

        :param indices: A list of Method indices for the self.method variable.
        :type  indices: list[int]

        :return: A list of Methods for running.
        :rtype:  list[sar.Method]
        """

        self.run_methods = [self.methods[int(i) - 1] for i in indices]
        return self.run_methods

class SARToolbox:

    def __init__(self, eod, record_ids=None, out_fn=None):
        
        self.eod = eod

        # schema_url = "https://github.com/eodms-sgdot/eodms-cli/blob/" \
        #             "development/schemas/SAR_Toolbox_Schema.json?raw=true"
        schema_url = "https://eodms-sgdot.nrcan-rncan.gc.ca/schemas/st/" \
                    "sar-toolbox-schema.json"
        with urllib.request.urlopen(schema_url) as response:
            self.schema_json = json.loads(response.read())

        # if record_ids:
        #     self.coll_id, rec_ids = record_ids.split(':')
        #     self.record_ids = rec_ids.split('|')
        self.record_ids = record_ids
        
        # self.constants = None
        self.out_fn = out_fn
        self.full_request = None

        self.categories = list()
        self.category_runs = list()

        self._add_categories()

        param_info = {
            "param_id": "Polarization",
            "label": "Polarization",
            "data_type": "list",
            "constants_key": "polarizations",
        }
        self.polarization = Parameter(param_info, multiple=True)
        
        self.logger = logging.getLogger('eodms')

    def set_coll_id(self, coll_id):
        """
        Sets the Collection Id for the SAR Toolbox order.

        :param coll_id: The Collection Id.
        :type  coll_id: str
        """

        self.coll_id = coll_id

    def set_record_ids(self, record_ids):
        """
        Sets the Record Ids for the SAR Toolbox order.

        :param record_ids: The Record Id(s).
        :type  record_ids: str
        """

        self.record_ids = record_ids

    def ingest_request(self, json_fn=None):
        """
        Gets the VAP Request from a JSON file.

        :param json_fn: The JSON filename with the VAP Request. 
                        If not specified, the self.out_fn is used.
        :type  json_fn: str
        """

        if not json_fn:
            json_fn = self.out_fn

        with open(json_fn) as f:
            self.full_request = json.load(f)

    def get_cat_names(self, with_ids=False):
        """
        Gets a list of Category names.

        :return: A list of SAR Toolbox Category names.
        :rtype:  list[str]
        """

        if with_ids:
            return [f"{c.name} ({c.id})" for c in self.categories]

        return [c.name for c in self.categories]
    
    # def get_method_names(self):
    #     return [m.name for m in self.category.get_methods()]
    
    # def get_methods(self):
    #     if self.category:
    #         return self.category.get_methods()
        
    # def get_arguments(self):
    #     if self.method:
    #         return self.method.get_arguments()

    # def get_products(self):
    #     if self.method:
    #         return self.method.get_products()

    def get_constants(self, const_key, include_inactive=False):
        """
        Gets a list of the available constants for a specific key.

        :param const_key: The constants key for the CONSTANTS dictionary.
        :type  const_key: str
        :param include_inactive: Determines whether to include inactive 
                                contants.
        :type  include_inactive: bool

        :return: A list of the available constants for a specific key.
        :rtype:  list[dict]
        """

        out_lst = list()
        
        const_vals = CONSTANTS.get(const_key)
        const_vals = sorted(const_vals, key=lambda d: d['display_order'])

        for c in const_vals:
            is_active = c.get('active')
            if not is_active and not include_inactive:
                continue
            out_lst.append(c)

        return out_lst

    def get_polarization_param(self):
        """
        Gets the polarization parameter.

        :return: The polarization parameter.
        :rtype:  sar.Parameter
        """

        return self.polarization
    
    def get_request(self):
        """
        Creates the VAP Request of the SAR Toolbox order for the RAPI.

        :return: The VAP Request JSON.
        :rtype:  dict
        """

        if self.full_request:
            return self.full_request

        self.full_request = dict()
        method_dict = dict()
        sequence_dict = dict()

        user_mdata = self.eod.eodms_rapi.get_metadata()

        user_id = user_mdata.get('authenticatedUser')

        items = []
        for rec_id in self.record_ids:
            item = {
                "collectionId": self.coll_id,
                "recordId": rec_id,
                "parameters": {}
                #     "NOTIFICATION_EMAIL_ADDRESS": ""
                # }
            }
            items.append(item)

        self.full_request["items"] = items
        self.full_request["destinations"] = []

        for cat in self.category_runs:
            cat_id = cat.get_id()
            for method in cat.get_method_runs():
                method_id = method.get_id()
                method_key = f"method-{method_id}-1"
                # label_name = method.name
                method_json = {
                    "Category": str(cat_id),
                    "Method": str(method_id)
                }

                # Set the output spacing
                if method_id == 301 or method_id == 303:
                    space_param = method.get_parameter("OutputPixSpacing")
                    if space_param:
                        space_val = space_param.get_value(True)
                        met_param = space_param.get_sub_param(
                                            "OutputPixSpacingMeters")
                        deg_param = space_param.get_sub_param(
                                            "OutputPixSpacingDeg")
                        if space_val.lower() == "meters":
                            deg_val = self.metres_to_degrees(
                                            met_param.get_value())
                            deg_param.set_value(deg_val)
                        elif space_val.lower() == "degrees":
                            met_val = self.degrees_to_metres(
                                            deg_param.get_value())
                            met_param.set_value(met_val)

                for param in method.get_param_runs():
                    param_key = param.param_id
                    value = param.get_value()
                    if param.data_type == "bool":
                        value = param.get_value(True)
                    if not value or value == 'off':
                        continue
                    # if not param.ignore:
                    if not param_key == "OutputPixSpacing":
                        method_json[param_key] = value

                    sub_params = param.get_sub_param()
                    if sub_params:
                        for s_param in sub_params:
                            sub_param_key = s_param.param_id
                            sub_value = s_param.get_value()
                            if s_param.data_type == "bool":
                                sub_value = s_param.get_value(True)
                            if not sub_value or sub_value == 'off':
                                continue
                            method_json[sub_param_key] = str(sub_value)

                for prod in method.get_prod_runs():
                    prod_id = prod.get_id()
                    prod_key = f"Product-{prod_id}"
                    method_json[prod_key] = "on"

                method_dict[method_key] = method_json

                seq_idx = len(sequence_dict.values()) + 1
                sequence_name = f"sequence_{seq_idx}"
                sequence_dict[sequence_name] = method_json.get('LabelName')

        vap_request = {
            "sequence": sequence_dict,
            "method": method_dict,
            "deliveryLocation": "DOWNLOAD"
        }

        pols = self.polarization.value
        pol_uid = [pol.get('uid_name') 
                   for pol in CONSTANTS.get('polarizations') 
                   if pol.get('label') in pols]
        for p in pol_uid:
            vap_request[p] = "on"
            
        vap_request["pr_users_username"] = user_id

        self.full_request['vapRequest'] = vap_request

        self.logger.info(f"Saving SAR Toolbox request to {self.out_fn}")
        if self.out_fn:
            with open(self.out_fn, 'w', encoding='utf-8') as f:
                json.dump(self.full_request, f, ensure_ascii=False, indent=4)

        return self.full_request
    
    # def set_category(self, name):
    #     available_cats = [c for c in self.categories if c.name == name]

    #     if len(available_cats) > 0:
    #         self.category = available_cats[0]

    def _get_latitude(self):
        """
        Gets the latitude value of the image using the RAPI.

        :return: The latitude of the centroid of the image.
        :rtype:  float
        """

        rapi = self.eod.get_rapi()
        rec_id = self.record_ids[0]

        res = rapi.get_record(self.coll_id, rec_id)

        feat = json.dumps(res.get('geometry'))
        centroid = self.eod.eodms_geo.get_centroid(feat)
        lat = centroid.y

        return lat

    def metres_to_degrees(self, metres):
        """
        Converts metres to degrees.

        :param metres: The metres value.
        :type  metres: int
        
        :return: The converted degrees value.
        :rtype:  float
        """
        
        lat = self._get_latitude()
        deg = self.eod.eodms_geo.metres_to_degrees(metres, lat)

        return deg
    
    def degrees_to_metres(self, deg):
        """
        Converts degrees to metres.

        :param deg: The degrees value.
        :type  deg: float
        
        :return: The converted metres value.
        :rtype:  float
        """
        
        lat = self._get_latitude()
        metres = self.eod.eodms_geo.degrees_to_metres(deg, lat)

        return metres

    def set_category_runs(self, indices):
        """
        Sets the Categories to run for the SAR Toolbox order based on the 
        given indices.

        :param indices: A list of indices for the Categories to run based on
                        the self.categories list.
        :type  indices: list

        :return: The list of Category runs.
        :rtype:  list[sar.Category]
        """

        self.category_runs = [self.categories[int(i) - 1] for i in indices]
        return self.category_runs

    def set_output_fn(self, fn):
        """
        Sets the filename of the output file.

        :param fn: The filename string to set.
        :type  fn: str
        """

        self.out_fn = fn

    # def set_products(self, in_prods):
    #     """
        
    #     """

    #     if isinstance(in_prods, str):
    #         self.product_choices = []
    #         for prod in self.method.get_products():
    #             for in_prod in in_prods:
    #                 if in_prod.name == prod.name:
    #                     self.product_choices.append(prod)
    #     else:
    #         self.product_choices = in_prods
        
    def _add_categories(self):
        """
        Creates the categories, methods, parameters and products using the 
        JSON schema from the Github repository.
        """

        for category in self.schema_json.get('categories'):
            cat_id = category.get('category_id')
            cat_name = category.get('name')
            
            methods = list()
            for method in category.get('methods'):
                method_id = method.get('method_id')
                method_name = method.get('name')

                params = list()
                if method.get('params'):
                    for param in method.get('params'):
                        if param.get('param_id') == 'LabelName':
                            param['default'] = f"My {method_name}"
                            
                        params.append(Parameter(param))

                products = list()
                if method.get('products'):
                    for prod in method.get('products'):
                        products.append(Product(prod))

                methods.append(Method(method_id, method_name, params, products))

            self.categories.append(Category(cat_id, cat_name, methods))