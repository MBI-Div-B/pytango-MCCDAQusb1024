#!/usr/bin/env python3

from gzip import WRITE
import tango
from tango import DevState, Attr, READ, WRITE
from tango.server import Device, command, device_property

from uldaq import (get_daq_device_inventory, DaqDevice, InterfaceType,
                   DigitalDirection, DigitalPortIoType)


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
            self.port_configs = [self.Port_A_config, self.Port_B_config, self.Port_C_config, self.Counter_enable]
            self.port_names = ['A', 'B', 'C', 'CTR']

            if self.dio_device is None:
                self.set_state(DevState.ALARM)
                self.set_status('Error: The DAQ device does not support digital input')
            else:
                # Establish a connection to the DAQ device.
                self.descriptor = self.daq_device.get_descriptor()
                self.daq_device.connect(connection_code=0)
                self.set_state(DevState.ON)
                self.info_stream('Establish a connection to the DAQ device {:s}'.format(self.descriptor.dev_string))

    def initialize_dynamic_attributes(self):
        # create automaticly attributes
        self.info_stream('Init dynamic attribute')        
        DYN_ATTRS = []
        # init DIO ports
        for port_type, port_name, port_config in zip(self.port_types, self.port_names, self.port_configs):
            if port_name == 'CTR' and port_config:
                port = dict(name=port_name, dtype=tango.DevBoolean, access=READ)
                DYN_ATTRS.append(port)
                self.info_stream('Initialized CTR')
            else:
                if port_config == 1:
                    # port configured as DI
                    self.dio_device.d_config_port(port_type, DigitalDirection.INPUT)
                    self.info_stream('{:s} configured as DI'.format(port_name))
                    for j in range(8):
                        name = '{:s}{:d}'.format(port_name, j)
                        port = dict(name=name, 
                                    dtype=tango.DevBoolean, access=READ)
                        DYN_ATTRS.append(port)
                        self.info_stream('Initialized DI {:s}'.format(name))
                elif port_config == 2:
                    # port configured as D0
                    self.dio_device.d_config_port(port_type, DigitalDirection.OUTPUT)
                    self.info_stream('{:s} configured as DO'.format(port_name))
                    for j in range(8):
                        name = '{:s}{:d}'.format(port_name, j)
                        port = dict(name=name, 
                                    dtype=tango.DevBoolean, access=WRITE)
                        DYN_ATTRS.append(port)
                        self.info_stream('Initialized DO {:s}'.format(name))
                else:
                    # port disabled
                    self.info_stream('Port {:s} not configured'.format(port_name))

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
                self.error_stream('Error setting attribute property: {:s}'.format(name))
        new_attr.set_default_properties(default_props)
        if access == READ:
            self.add_attribute(new_attr, r_meth=self.read_general)
            if name == 'CTR':
                self.info_stream('Added dynamic attribute {:s} as counter'.format(name))
            else:
                self.info_stream('Added dynamic attribute {:s} as DI'.format(name))
        elif access == WRITE:
            self.add_attribute(new_attr, w_meth=self.write_general)
            self.info_stream('Added dynamic attribute {:s} as DO'.format(name))
        else:
            self.error_stream('Only READ or WRITE access types are supported!')            

    def write_general(self, attr):
        self.debug_stream(attr.get_name())
        val = attr.get_write_value()

    def read_general(self, attr):        
        self.debug_stream(attr.name)
        port_index = 7-int(attr.name[1])
        self.debug_stream(port_index)
        attr.set_value(False)
    #     # read out data
    #     # data is passed as a byte for each port_type and every bit represents a port; 1.bit = 1.port of port_type ...
    #     key=7-int(list(attr.get_name())[1])
    #     port_type = list(attr.get_name())[0]
    #     # port_types_index: 0 = PortA, 1 = PortB, 2 = PortC)
    #     if port_type == 'A':
    #         port_types_index = 0
    #     elif port_type == 'B':
    #         port_types_index = 1
    #     elif port_type == 'C':
    #         port_types_index = 2
    #     else:
    #         port_types_index = 3 #this is the counter

    #     attr.set_value(self.data_get(key, port_types_index))

    # def data_get(self, key, port_types_index):
    #     #function to communicate with port_type input
        
    #     # Get the port types for the device(AUXPORT, FIRSTPORTA, ...)
    #     self.dio_info = self.dio_device.get_info()
    #     self.port_types = self.dio_info.get_port_types()

    #     # [<DigitalPortType.FIRSTPORTA: 10>, <DigitalPortType.FIRSTPORTB: 11>,
    #     # <DigitalPortType.FIRSTPORTC: 12>, <DigitalPortType.FIRSTPORTCH: 13>]
        
    #     if port_types_index >= len(self.port_types):
    #         port_types_index = len(self.port_types) - 1

    #     self.port_to_read = self.port_types[port_types_index]
        
    #     # Configure the port for input.
    #     self.port_info = self.dio_info.get_port_info(self.port_to_read)

    #     if (self.port_info.port_io_type == DigitalPortIoType.IO or
    #             self.port_info.port_io_type == DigitalPortIoType.BITIO):
    #         self.dio_device.d_config_port(self.port_to_read, DigitalDirection.INPUT)
        
    #     self.set_state(DevState.RUNNING)
    #     self.set_status('Reading data')
    #     self.data = self.dio_device.d_in(self.port_to_read)
    #     if port_types_index==3:
    #         return self.data
    #     else:
    #         data_bit_list=list(format(self.data,'08b'))
    #         if int(data_bit_list[key]) == 0:
    #             return False
    #         else:
    #             return True
        
    def delete_device(self):
        if self.daq_device:
            if self.daq_device.is_connected():
                self.daq_device.disconnect()
            self.daq_device.release()


if __name__ == '__main__':
    MCCDAQusb1024.run_server()