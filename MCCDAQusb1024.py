#!/usr/bin/env python3

import tango
from tango import DevState, Attr, READ, WRITE
from tango.server import Device, device_property
from uldaq import (get_daq_device_inventory, DaqDevice, InterfaceType,
                   DigitalDirection)


class MCCDAQusb1024(Device):

    # properties
    Port_A_config = device_property(
        dtype=int,
        default_value=1,
        doc='0 - disabled; 1 - digital input; 2 - digital output',
        )

    Port_B_config = device_property(
        dtype=int,
        default_value=1,
        doc='0 - disabled; 1 - digital input; 2 - digital output',
        )

    Port_C_config = device_property(
        dtype=int,
        default_value=1,
        doc='0 - disabled; 1 - digital input; 2 - digital output',
        )

    Counter_enable = device_property(
        dtype=bool,
        default_value=True,
        doc='enable counter'
        )

    Descriptor_index = device_property(
        dtype=int,
        default_value=0
        )

    def init_device(self):
        Device.init_device(self)
        self.set_state(DevState.INIT)
        # type of the communication interface
        interface_type = InterfaceType.ANY

        # Get descriptors for all of the available DAQ devices.
        self.devices = get_daq_device_inventory(interface_type)
        self.number_of_devices = len(self.devices)
        if self.number_of_devices == 0:
            self.set_state(DevState.ALARM)
            self.set_status('Error: No DAQ devices found')
        else:
            # Create the DAQ device from the descriptor at the specified index.
            self.daq_device = DaqDevice(self.devices[self.Descriptor_index])

            # Get the DioDevice object and verify that it is valid.
            self.dio_device = self.daq_device.get_dio_device()

            self.dio_info = self.dio_device.get_info()
            self.port_types = self.dio_info.get_port_types()
            self.port_configs = [self.Port_A_config, self.Port_B_config,
                                 self.Port_C_config, self.Counter_enable]
            self.port_names = ['A', 'B', 'C', 'CTR']

            if self.dio_device is None:
                self.set_state(DevState.ALARM)
                self.set_status('Error: The DAQ device does \
                    not support digital input')
            else:
                # Establish a connection to the DAQ device.
                self.descriptor = self.daq_device.get_descriptor()
                self.daq_device.connect(connection_code=0)
                self.set_state(DevState.ON)
                self.info_stream('Establish a connection to the DAQ \
                    device {:s}'.format(self.descriptor.dev_string))

    def initialize_dynamic_attributes(self):
        # create automaticly attributes
        self.info_stream('Init dynamic attribute')
        DYN_ATTRS = []
        # init DIO ports
        for port_type, port_name, port_config in zip(self.port_types,
                                                     self.port_names,
                                                     self.port_configs):
            if port_name == 'CTR' and port_config:
                port = dict(name=port_name, dtype=tango.DevBoolean,
                            access=READ)
                DYN_ATTRS.append(port)
                self.info_stream('Initialized CTR')
            else:
                if port_config == 1:
                    # port configured as DI
                    self.dio_device.d_config_port(port_type,
                                                  DigitalDirection.INPUT)
                    self.info_stream('{:s} configured as DI'.format(port_name))
                    for j in range(8):
                        name = '{:s}{:d}'.format(port_name, j)
                        port = dict(name=name,
                                    dtype=tango.DevBoolean, access=READ)
                        DYN_ATTRS.append(port)
                        self.info_stream('Initialized DI {:s}'.format(name))
                elif port_config == 2:
                    # port configured as D0
                    self.dio_device.d_config_port(port_type,
                                                  DigitalDirection.OUTPUT)
                    self.info_stream('{:s} configured as DO'.format(port_name))
                    for j in range(8):
                        name = '{:s}{:d}'.format(port_name, j)
                        port = dict(name=name,
                                    dtype=tango.DevBoolean, access=WRITE)
                        DYN_ATTRS.append(port)
                        self.info_stream('Initialized DO {:s}'.format(name))
                else:
                    # port disabled
                    self.info_stream('Port {:s} not \
                        configured'.format(port_name))

        if DYN_ATTRS:
            for d in DYN_ATTRS:
                self.make_attribute(d)
        else:
            self.warning_stream('No ports are selected.')

    def make_attribute(self, attr_dict):
        props = ['name', 'dtype', 'access']
        name, dtype, access = [attr_dict.pop(k) for k in props]
        new_attr = Attr(name, dtype, access)
        default_props = tango.UserDefaultAttrProp()

        # build attribute for all enabled ports
        for k, v in attr_dict.items():
            try:
                property_setter = getattr(default_props, 'set_' + k)
                property_setter(v)
            except AttributeError:
                self.error_stream('Error setting attribute \
                    property: {:s}'.format(name))
        new_attr.set_default_properties(default_props)
        if access == READ:
            if name == 'CTR':
                self.add_attribute(new_attr, r_meth=self.read_CTR)
                self.info_stream('Added dynamic attribute \
                    {:s} as counter'.format(name))
            else:
                self.add_attribute(new_attr, r_meth=self.read_DI)
                self.info_stream('Added dynamic attribute {:s} \
                    as DI'.format(name))
        elif access == WRITE:
            self.add_attribute(new_attr, w_meth=self.write_DO)
            self.info_stream('Added dynamic attribute {:s} \
                as DO'.format(name))
        else:
            self.error_stream('Only READ or WRITE access types \
                are supported!')

    def connector_info(self, attr):
        attr_name = attr.get_name()
        # index of the connector on the port
        connector_index = int(attr_name[1])
        # name of the port
        port_name = attr_name[0]
        # index of the port to read on the device
        port_index = self.port_names.index(port_name)
        return attr_name, port_name, connector_index, port_index

    def write_DO(self, attr):
        all_attr = self.get_device_attr()
        _, port_name, _, port_index = self.connector_info(attr)
        # acqurie data of all write values on the port
        bit_list = []
        for i in range(8):
            # get attribute by name
            port_attr = all_attr.get_attr_by_name('{:s}{:d}'.format(
                port_name, i))
            bit_list.append(int(port_attr.get_write_value()))
        # reverse order of bit list
        bit_list.reverse()
        # bit to int conversion
        data = int("".join(str(i) for i in bit_list), 2)
        self.debug_stream('Writing value {:d} to port {:s}'.format(
            data, port_name))
        # write value to port
        self.dio_device.d_out(self.port_types[port_index], data)

    def read_CTR(self, attr):
        # needs to be implemented
        pass

    def read_DI(self, attr):
        _, port_name, connector_index, port_index = self.connector_info(attr)
        # read the data of the whole port
        data = self.dio_device.d_in(self.port_types[port_index])
        self.debug_stream('Reading value {:d} from port {:s}'.format(
            data, port_name))
        # convert integer to list of binary strings
        data_bit_list = list(format(data, '08b'))
        # reverse order to match index of DIs
        data_bit_list.reverse()
        # the the value of the DI
        attr.set_value(int(data_bit_list[connector_index]))

    def delete_device(self):
        if self.daq_device:
            if self.daq_device.is_connected():
                self.daq_device.disconnect()
            self.daq_device.release()


if __name__ == '__main__':
    MCCDAQusb1024.run_server()
