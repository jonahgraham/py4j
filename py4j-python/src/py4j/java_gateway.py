# -*- coding: UTF-8 -*-
"""Module to interact with objects in a Java Virtual Machine from a Pyton Virtual Machine.

Created on Dec 3, 2009

@author: Barthelemy Dagenais
"""

import logging
from IN import AF_INET
from IN import SOCK_STREAM
import socket

class NullHandler(logging.Handler):
    def emit(self, record):
        pass

null_handler = NullHandler()
logging.getLogger("py4j").addHandler(null_handler)
logger = logging.getLogger("py4j.java_gateway")

BUFFER_SIZE = 4096
DEFAULT_PORT = 25333

# Entry point
ENTRY_POINT_OBJECT_ID = 't'

# Types
INTEGER_TYPE = 'i'
BOOLEAN_TYPE = 'b'
DOUBLE_TYPE = 'd'
STRING_TYPE = 's'
REFERENCE_TYPE = 'r'
LIST_TYPE = 'l'
NULL_TYPE = 'n'
VOID_TYPE = 'v'

# Protocol
END = 'e'
ERROR = 'x'
SUCCESS = 'y'

# Commands
CALL_COMMAND_NAME = 'c\n'
SHUTDOWN_GATEWAY_COMMAND_NAME = 's\n'
LIST_COMMAND_NAME = 'l\n'


# List subcommands
LIST_SORT_SUBCOMMAND_NAME = 's\n'
LIST_REVERSE_SUBCOMMAND_NAME = 'r\n'
LIST_SLICE_SUBCOMMAND_NAME = 'l\n'
LIST_CONCAT_SUBCOMMAND_NAME = 'a\n'
LIST_MULT_SUBCOMMAND_NAME = 'm\n'
LIST_IMULT_SUBCOMMAND_NAME = 'i\n'
LIST_COUNT_SUBCOMMAND_NAME = 'f\n'


def escape_new_line(original):
    """Replaces new line characters by a backslash followed by a n.
    
    Backslashes are also escaped by another backslash.
    
    :param original: the string to escape
    
    :rtype: an escaped string
    """
    temp = original.replace('\\', '\\\\')
    final = temp.replace('\n', '\\n')
    return final
    
def get_command_part(parameter):
    command_part = ''
    if parameter == None:
        command_part = NULL_TYPE
    elif isinstance(parameter, bool):
        command_part = BOOLEAN_TYPE + str(parameter)
    elif isinstance(parameter, int) or isinstance(parameter, long):
        command_part = INTEGER_TYPE + str(parameter)
    elif isinstance(parameter, float):
        command_part = DOUBLE_TYPE + str(parameter) 
    elif isinstance(parameter, basestring):
        command_part = STRING_TYPE + escape_new_line(parameter)
    else:
        command_part = REFERENCE_TYPE + parameter.get_object_id()
    
    return command_part + '\n'

def get_return_value(answer, comm_channel, target_id = None, name = None):
    if len(answer) == 0 or answer[0] != SUCCESS:
        raise Py4JError('An error occurred while calling %s%s%s' % (target_id, '.', name))
    elif answer[1] == NULL_TYPE:
        return None
    elif answer[1] == VOID_TYPE:
        return
    elif answer[1] == REFERENCE_TYPE:
        return JavaObject(answer[2:], comm_channel)
    elif answer[1] == LIST_TYPE:
        return JavaList(answer[2:], comm_channel)
    elif answer[1] == INTEGER_TYPE:
        return int(answer[2:])
    elif answer[1] == BOOLEAN_TYPE:
        return answer[2:].lower() == 'true'
    elif answer[1] == DOUBLE_TYPE:
        return float(answer[2:])
    elif answer[1] == STRING_TYPE:
        return answer[2:]

class Py4JError(Exception):
    """Exception thrown when a problem occurs with Py4J."""
    def __init__(self, value):
        """
        
        :param value: the error message
        """
        self.value = value
    
    def __str__(self):
        return repr(self.value)

class CommChannel(object):
    """Default communication channel (socket based) responsible for communicating with the Java Virtual Machine."""
    
    def __init__(self, address='localhost', port=25333, auto_close=True):
        """
        :param address: the address to which the comm channel will connect
        :param port: the port to which the comm channel will connect. Default is 25333.
        :param auto_close: if `True`, the communication channel closes the socket when it is garbage 
          collected (i.e., when `CommChannel.__del__()` is called).
        """
        self.address = address
        self.port = port
        self.socket = socket.socket(AF_INET, SOCK_STREAM)
        self.is_connected = False
        self.auto_close = auto_close
        
    def start(self):
        """Starts the communication channel by connecting to the `address` and the `port`"""
        self.socket.connect((self.address, self.port))
        self.is_connected = True
    
    def close(self, throw_exception=False):
        """Closes the communication channel by closing the socket."""
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()
        except Exception as e:
            if throw_exception:
                raise e
        finally:
            self.is_connected = False
        
    def shutdown_gateway(self):
        """Sends a shutdown command to the gateway. This will close the gateway server: all active 
        connections will be closed. This may be useful if the lifecycle of the Java program must be 
        tied to the Python program."""
        try:
            self.socket.sendall(SHUTDOWN_GATEWAY_COMMAND_NAME.encode('utf-8'))
            self.socket.close()
            self.is_connected = False
        except Exception:
            # Do nothing! Exceptions might occur anyway.
            pass

    def __del__(self):
        """Closes the socket if auto_delete is True and the socket is opened. 
        
        This is an acceptable practice if you know that your Python VM implements garbage collection 
        and closing sockets immediately is not a concern. Otherwise, it is always better (because it 
        is predictable) to explicitly close the socket by calling `CommChannel.close()`.
        """
        if self.auto_close and self.socket != None and self.is_connected:
            self.close()
        
    def send_command(self, command):
        """Sends a command to the JVM. This method is not intended to be called directly by Py4J users: it is usually called by JavaMember instances.
        
        :param command: the `string` command to send to the JVM. The command must follow the Py4J protocol.
        :rtype: the `string` answer received from the JVM. The answer follows the Py4J protocol.
        """
        
        logger.debug("Command to send: %s" % (command))
        self.socket.sendall(command.encode('utf-8'))
        answer = self.socket.recv(BUFFER_SIZE).decode('utf-8')
        logger.debug("Answer received: %s" % (answer))
        return answer

class JavaMember(object):
    """Represents a member (field, method) of a Java Object. For now, only methods are supported.
    """
    
    def __init__(self, name, target_id, comm_channel):
        self.name = name
        self.target_id = target_id
        self.comm_channel = comm_channel
        self.command_header = self.target_id + '\n' + self.name + '\n'
        
    def __call__(self, *args):
        args_command = ''.join([get_command_part(arg) for arg in args])
        command = CALL_COMMAND_NAME + self.command_header + args_command + END + '\n'
        answer = self.comm_channel.send_command(command)
        return_value = get_return_value(answer, self.comm_channel, self.target_id, self.name)
        return return_value



class JavaObject(object):
    """Represents a Java object from which you can call methods."""
    
    def __init__(self, target_id, comm_channel):
        """
        :param target_id: the identifier of the object on the JVM side. Given by the JVM.
        :param comm_channel: the communication channel used to communicate with the JVM.
        """
        self.target_id = target_id
        self.methods = {}
        self.comm_channel = comm_channel
        
    def get_object_id(self):
        return self.target_id
        
    def __getattr__(self, name):
        if name not in self.methods:
            self.methods[name] = JavaMember(name, self.target_id, self.comm_channel)
        return self.methods[name]
    
    def __eq__(self, other):
        if other == None:
            return False
        else:
            return self.equals(other)
    
    def __hash__(self):
        return self.hashCode()
    
    def __str__(self):
        return self.toString()
    
    def __repr__(self):
        # For now...
        return self.toString()
    
class JavaListIterator(JavaObject):
    """Maps a Python list iterator to a Java list iterator.
    
    The `JavaListIterator` follows the Python iterator protocol and raises a `StopIteration` error when the iterator can no longer iterate."""
    def __init__(self, target_id, comm_channel):
        JavaObject.__init__(self, target_id, comm_channel)
        self.next_name = 'next'
        
    def __iter__(self):
        return self
    
    def next(self):
        if self.next_name not in self.methods:
            self.methods[self.next_name] = JavaMember(self.next_name, self.target_id, self.comm_channel)
        try:
            return self.methods[self.next_name]()
        except Py4JError:
            raise StopIteration()
    
class JavaList(JavaObject):
    """Maps a Python list to a Java list.
    
    All operations possible on a Python list are implemented. For example, slicing (e.g., list[1:3]) 
    will create a copy of the list on the JVM. Slicing is thus not equivalent to subList(), because 
    a modification to a slice such as the addition of a new element will not affect the original 
    list."""
    
    def __init__(self, target_id, comm_channel):
        JavaObject.__init__(self, target_id, comm_channel)

    def __len__(self):
        return self.size()

    def __iter__(self):
        return JavaListIterator(self.iterator().get_object_id(), self.comm_channel)
    
    def __compute_index(self, key, adjustLast = False):
        size = self.size()
        if 0 <= key < size:
            return key
        elif key < 0 and abs(key) <= size:
            return size + key
        elif adjustLast:
            return size
        else:
            raise IndexError("list index out of range")
    
    def __compute_item(self, key):
        new_key = self.__compute_index(key)
        return self.get(new_key)
    
    def __set_item(self, key, value):
        new_key = self.__compute_index(key)
        self.set(new_key, value)

    def __set_item_from_slice(self, indices, iterable):
        offset = 0
        last = 0
        value_iter = iter(iterable)
        
        # First replace and delete if from_slice > to_slice
        for i in range(*indices):
            try:
                value = value_iter.next()
                self.__set_item(i, value)
            except StopIteration:
                self.__del_item(i)
                offset -= 1
            last = i + 1
        
        # Then insert if from_slice < to_slice 
        for elem in value_iter:
            self.insert(last,elem)
            last += 1
    
    def __insert_item_from_slice(self, indices, iterable):
        index = indices[0]
        for elem in iterable:
            self.insert(index,elem)
            index += 1
    
    def __repl_item_from_slice(self, range, iterable):
        value_iter = iter(iterable)
        for i in range:
            value = value_iter.next()
            self.__set_item(i, value)
            
    def __append_item_from_slice(self, range, iterable):
        for value in iterable:
            self.append(value)
    
    def __del_item(self, key):
        new_key = self.__compute_index(key)
        self.remove(new_key)

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            self_len = len(self)
            indices = key.indices(self_len)
            if indices[0] >= self_len:
                self.__append_item_from_slice(range, value)
            elif indices[0] == indices[1]:
                self.__insert_item_from_slice(indices, value)
            elif indices[2] == 1:
                self.__set_item_from_slice(indices, value)
            else:
                self_range = range(*indices)
                lenr = len(self_range)
                lenv = len(value)
                if lenr != lenv:
                    raise ValueError("attempt to assign sequence of size %d to extended slice of size %d" % (lenv,lenr))
                else:
                    return self.__repl_item_from_slice(self_range,value)
            
        elif isinstance(key, int):
            return self.__set_item(key, value)
        else:
            raise TypeError("list indices must be integers, not %s" % key.__class__.__name__)
    
    def __get_slice(self, indices):
        command = LIST_COMMAND_NAME + LIST_SLICE_SUBCOMMAND_NAME + self.get_object_id() + '\n'
        for index in indices:
            command += get_command_part(index)
        command += END + '\n'
        answer = self.comm_channel.send_command(command)
        return get_return_value(answer, self.comm_channel)
        
        
    def __getitem__(self, key):
        if isinstance(key, slice):
            indices = key.indices(len(self))
            return self.__get_slice(range(*indices))
        elif isinstance(key, int):
            return self.__compute_item(key)
        else:
            raise TypeError("list indices must be integers, not %s" % key.__class__.__name__)
        
    def __delitem__(self, key):
        if isinstance(key, slice):
            indices = key.indices(len(self))
            offset = 0
            for i in range(*indices):
                self.__del_item(i + offset)
                offset -= 1 
        elif isinstance(key, int):
            return self.__del_item(key)
        else:
            raise TypeError("list indices must be integers, not %s" % key.__class__.__name__)
    
    def __contains__(self, item):
        return self.contains(item)
        
    def __add__(self, other):
        command = LIST_COMMAND_NAME + LIST_CONCAT_SUBCOMMAND_NAME + self.get_object_id() + '\n' + other.get_object_id() + '\n' + END + '\n'
        answer = self.comm_channel.send_command(command)
        return get_return_value(answer, self.comm_channel)
    
    def __radd__(self, other):
        return self.__add__(other)
    
    def __iadd__(self, other):
        self.extend(other)
        return self
    
    def __mul__(self, other):
        command = LIST_COMMAND_NAME + LIST_MULT_SUBCOMMAND_NAME + self.get_object_id() + '\n' + get_command_part(other) + END + '\n'
        answer = self.comm_channel.send_command(command)
        return get_return_value(answer, self.comm_channel)
    
    def __rmul__(self, other):
        return self.__mul__(other)
    
    def __imul__(self, other):
        command = LIST_COMMAND_NAME + LIST_IMULT_SUBCOMMAND_NAME + self.get_object_id() + '\n' + get_command_part(other) + END + '\n'
        self.comm_channel.send_command(command)
        return self
        
    def append(self, value):
        self.add(value)
        
    def insert(self, key, value):
        if isinstance(key, int):
            new_key = self.__compute_index(key, True)
            return self.add(new_key, value)
        else:
            raise TypeError("list indices must be integers, not %s" % key.__class__.__name__)
        
    def extend(self, other_list):
        self.addAll(other_list)

    def pop(self, key=None):
        if key == None:
            new_key = self.size() - 1
        else:
            new_key = self.__compute_index(key) 
        return self.remove(new_key);
    
    def index(self, value):
        return self.indexOf(value)
    
    def count(self, value):
        command = LIST_COMMAND_NAME + LIST_COUNT_SUBCOMMAND_NAME + self.get_object_id() + '\n' + get_command_part(value) + END + '\n'
        answer = self.comm_channel.send_command(command)
        return get_return_value(answer, self.comm_channel)
    
    def sort(self):
        command = LIST_COMMAND_NAME + LIST_SORT_SUBCOMMAND_NAME + self.get_object_id() + '\n' + END + '\n'
        self.comm_channel.send_command(command)
    
    def reverse(self):
        command = LIST_COMMAND_NAME + LIST_REVERSE_SUBCOMMAND_NAME + self.get_object_id() + '\n' + END + '\n'
        self.comm_channel.send_command(command)
    
    # remove is automatically supported by Java...
    
    def __str__(self):
        return self.__repr__()
    
    def __repr__(self):
        # TODO Make it more efficient/pythonic
        # TODO Debug why strings are not outputed with apostrophes.
        if len(self) == 0:
            return '[]'
        else:
            srep = '['
            for elem in self:
                srep += repr(elem) + ', '
                
            return srep[:-2] + ']'

class JavaGateway(JavaObject):
    """A `JavaGateway` is the main interaction point between a Python VM and a JVM. 
    
    * A `JavaGateway` instance is connected to a `Gateway` instance on the Java side.
    
    * The `entry_point` field of a `JavaGateway` instance is connected to the `Gateway.entryPoint` instance on the Java side.
    
    Methods that are not defined by `JavaGateway` are always redirected to `entry_point`. For example, ``gateway.doThat()`` is equivalent to ``gateway.entry_point.doThat()``.
    This is a trade-off between convenience and potential confusion."""
    
    
    def __init__(self, comm_channel=None, auto_start=True):
        """
        :param comm_channel: communication channel used to connect to the JVM. If `None`, a communication channel based on a socket with the default parameters is created.
        :param auto_start: if `True`, the JavaGateway connects to the JVM as soon as it is created. Otherwise, you need to explicitly call `gateway.comm_channel.start()`.
        """
        if comm_channel == None:
            comm_channel = CommChannel()
            
        JavaObject.__init__(self, ENTRY_POINT_OBJECT_ID, comm_channel)
        self.entry_point = JavaObject(ENTRY_POINT_OBJECT_ID, comm_channel)
        if auto_start:
            self.comm_channel.start()
            
    def shutdown(self):
        self.comm_channel.shutdown_gateway()
