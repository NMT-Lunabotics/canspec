"""CAN serialization engine compatible with KCD."""

import math

from typing import Any, Union, List, Tuple, Dict, Callable, TypeVar, Iterable
from _xml import XML


class KCDMessageSerializer:
    """Class to serialize a KCD file, and keep track of bit offset."""

    def __init__(self) -> None:
        """Initialize."""
        self.bit_pos = 0
        self.contents: List[XML] = []

    def write(self, xml: XML, size: int) -> None:
        """Write a new XML node to the KCD, and advance the bit position."""
        self.contents.append(xml)
        self.bit_pos += size


class CANSemanticException(Exception):
    """Semantic error in a YAML CAN definition."""


class CANSignal:
    """A single, non-label signal in a CAN message."""

    def __init__(self, params: Any) -> None:
        """Load from YAML."""
        self.unit = params['unit'] if 'unit' in params else ''
        self.min: int = params['range'][0]
        self.max: int = params['range'][1]
        self.size: int = params['size'] if 'size' in params else 8

    def slope(self) -> float:
        """Slope of the linear equation."""
        input_range: float = 2 ** self.size - 1
        output_range = self.max - self.min
        return output_range / input_range

    def serialize_kcd(
            self,
            serializer: KCDMessageSerializer,
            name: str,
    ) -> None:
        """Serialize to a KCD file."""
        serializer.write(
            XML(
                'Signal',
                {
                    'name': name,
                    'offset': str(serializer.bit_pos),
                    'length': str(self.size),
                },
                [XML(
                    'Value',
                    {
                        'type': 'unsigned',
                        'unit': self.unit,
                        'slope': str(self.slope()),
                        'intercept': str(self.min),
                        'min': str(self.min),
                        'max': str(self.max),
                    },
                )],
            ),
            self.size,
        )


class CANStruct:
    """A struct or message from a CAN definition file.

    This can either contain members like a struct, or it can be an
    enum.

    """

    def __init__(self, name: str, yaml: Any) -> None:
        """Load from YAML."""
        self.name = name

        if isinstance(yaml, list):
            # Struct.
            self.is_enum = False
            self.struct_members: List[Tuple[str, Union[CANSignal, str]]] = (
                list(map(
                    lambda member: (
                        list(member.keys())[0],
                        CANStruct._member_type_to_signal(
                            list(member.values())[0]
                        ),
                    ),
                    yaml,
                ))
            )
        elif isinstance(yaml, dict):
            # Enum.
            if list(yaml.keys()) != ['enum']:
                raise CANSemanticException(f'Invalid struct def: {yaml}')
            self.is_enum = True
            self.enum_members: List[str] = yaml['enum']

    @staticmethod
    def _member_type_to_signal(yaml: Any) -> Union[CANSignal, str]:
        """Convert a yaml type to a CANSignal or struct name."""
        if isinstance(yaml, str):
            return yaml
        else:
            return CANSignal(yaml)

    def dependencies(self) -> List[str]:
        """List the dependencies on other structures.

        This method filters out the built-in structure `bool`.

        """
        built_in = ['bool']

        if self.is_enum:
            return []
        else:
            deps: List[str] = []
            for name, member in self.struct_members:
                if isinstance(member, str) and member not in built_in:
                    deps.append(member)
            return deps

    def size(self, struct_defs: Dict[str, 'CANStruct']) -> int:
        """Size of the struct, in bits."""
        if self.is_enum:
            return math.ceil(math.log2(len(self.enum_members)))
        else:
            total = 0
            for name, member in self.struct_members:
                if isinstance(member, CANSignal):
                    total += member.size
                else:
                    total += struct_defs[member].size(struct_defs)
            return total

    def __repr__(self) -> str:
        """Get string representation."""
        if self.is_enum:
            return f'<CAN enum {self.enum_members}>'
        else:
            return f'<CAN struct {self.struct_members}>'

    def serialize_members_kcd(
            self,
            serializer: KCDMessageSerializer,
            struct_defs: Dict[str, 'CANStruct'],
            name_base: str = '',
    ) -> None:
        """Serialize members to a KCD file."""
        if self.is_enum:
            serializer.write(
                XML(
                    'Signal',
                    {
                        'name': name_base.rstrip('_'),
                        'offset': str(serializer.bit_pos),
                        'length': str(self.size({})),
                    },
                    [XML(
                        'LabelSet',
                        children=list(map(
                            lambda member: XML(
                                'Label',
                                {
                                    'name': member[1],
                                    'value': str(member[0]),
                                }
                            ),
                            enumerate(self.enum_members),
                        ))
                    )],
                ),
                self.size({})
            )
        else:
            for member in self.struct_members:
                if isinstance(member[1], CANSignal):
                    member[1].serialize_kcd(serializer, name_base + member[0])
                elif member[1] == 'bool':
                    serializer.write(
                        XML(
                            'Signal',
                            {
                                'name': name_base + member[0],
                                'offset': str(serializer.bit_pos),
                                'length': '1',
                            },
                            [XML(
                                'Value',
                                {
                                    'type': 'unsigned',
                                },
                            )]
                        ),
                        1,
                    )
                else:
                    struct_defs[member[1]].serialize_members_kcd(
                        serializer,
                        struct_defs,
                        name_base + member[0] + '_'
                    )

    def serialize_message_kcd(
            self,
            struct_defs: Dict[str, 'CANStruct'],
            id: int,
    ) -> XML:
        """Serialize to a KCD file as a message."""
        serializer = KCDMessageSerializer()
        self.serialize_members_kcd(serializer, struct_defs)
        return XML(
            'Message',
            {
                'id': str(id),
                'name': self.name,
            },
            serializer.contents,
        )

    def serialize_cpp(
            self,
            output: Callable[[str], None],
            struct_defs: Dict[str, 'CANStruct'],
    ) -> None:
        """Serialize to a C++ header."""
        if self.is_enum:
            output(f'enum class {self.name} {{')
            for idx, item in enumerate(self.enum_members):
                output(f'  {item} = {idx},')
            output('};')

            # Use simple casting to convert.
            output('')
            output(f'inline {self.name} {self.name}_deserialize(' +
                   'uint64_t buffer) {')
            output(f'  return ({self.name})buffer;')
            output('}')

            output('')
            output(f'inline uint64_t serialize({self.name} data) {{')
            output('  return (uint64_t)data;')
            output('}')

            # Formatted output.
            output('')
            output('inline std::ostream &operator<<(std::ostream &os, const '
                   f'{self.name} &self) {{')
            output('  switch (self) {')
            for item in self.enum_members:
                output(f'  case {self.name}::{item}:')
                output(f'    os << "{self.name}::{item}";')
                output('    break;')
            output('  }')
            output('  return os;')
            output('}')
        else:
            output(f'struct {self.name} {{')
            for name, typ in self.struct_members:
                typename = 'double' if isinstance(typ, CANSignal) else typ
                output(f'  {typename} {name};')
            output('};')

            # Writing this as a constructor disallows aggregate
            # initialization, which we don't want. Writing it as a
            # static method results in an asymmetry since it's illegal
            # to put a static method on an enum. As far as I can tell,
            # the only remaining choice is to write it as an inline
            # function.
            output('')
            output(f'inline {self.name} {self.name}_deserialize(' +
                   'uint64_t buffer) {')
            output(f'  {self.name} self;')
            for name, typ in self.struct_members:
                if isinstance(typ, CANSignal):
                    output(
                        f'  self.{name} = (double)read(buffer, {typ.size})' +
                        f' * {typ.slope()} + {typ.min};'
                    )
                else:
                    if typ == 'bool':
                        size = 1
                    else:
                        size = struct_defs[typ].size(struct_defs)
                    output(
                        f'  self.{name} = {typ}_deserialize(' +
                        f'read(buffer, {size}));'
                    )
            output('  return self;')
            output('}')

            output('')
            output(f'inline uint64_t serialize({self.name} data) {{')
            output('  uint64_t ser = 0;')
            for name, typ in reversed(self.struct_members):
                if isinstance(typ, CANSignal):
                    value = f'(data.{name} - {typ.min}) / {typ.slope()}'
                    output(
                        f'  write(ser, {typ.size}, {value});'
                    )
                else:
                    if typ == 'bool':
                        size = 1
                    else:
                        size = struct_defs[typ].size(struct_defs)
                    output(
                        f'  write(ser, {size}, serialize(data.{name}));'
                    )
            output('  return ser;')
            output('}')

            # Formatted output.
            output('')
            output('inline std::ostream &operator<<(std::ostream &os, const '
                   f'{self.name} &self) {{')
            output('  return os << "{ "')
            for name, typ in self.struct_members:
                output(f'            << "{name} = " << self.{name} << ", "')
            output('            << "}";')
            output('}')


def database_to_kcd(database: Any) -> XML:
    """Convert a database YAML file to a KCD file."""
    struct_defs: Dict[str, CANStruct] = {}
    for struct_name in database['structs'].keys():
        struct_defs[struct_name] = CANStruct(
            struct_name,
            database['structs'][struct_name]
        )
    for struct_name in database['messages'].keys():
        struct_defs[struct_name] = CANStruct(
            struct_name,
            database['messages'][struct_name]
        )

    messages: List[XML] = []
    for id, struct_name in enumerate(database['messages'].keys()):
        messages.append(struct_defs[struct_name].serialize_message_kcd(
            struct_defs,
            id,
        ))

    return XML(
        'NetworkDefinition',
        {
            'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            # yes, it's a dead link.
            'xmlns': 'http://kayak.2codeornot2code.org/1.0',
            'xsi:noNamespaceSchemaLocation': 'Definition.xsd',
        },
        [
            XML(
                'Document',
                {
                    'name': database['name'],
                    'version': '1.0',
                    'author': 'autogenerated',
                    'date': '1970-01-01',
                },
                content='Autogenerated from canspec.'
            ),
            XML(
                'Bus',
                {'name': 'Main'},
                messages,
            ),
        ],
    )


def database_to_cpp(database: Any) -> str:
    """Convert a database YAML file to a C++ header file."""
    struct_defs: Dict[str, CANStruct] = {}
    for struct_name in database['structs'].keys():
        struct_defs[struct_name] = CANStruct(
            struct_name,
            database['structs'][struct_name]
        )
    for struct_name in database['messages'].keys():
        struct_defs[struct_name] = CANStruct(
            struct_name,
            database['messages'][struct_name]
        )

    out = ''

    def putline(line: str, end: str = '\n') -> None:
        nonlocal out
        out += line + '\n'

    putline('// Structures and conversions generated by can.py.')
    putline(f'#ifndef {database["name"]}_H')
    putline(f'#define {database["name"]}_H')

    # needed for uint64_t
    putline('#include <stdint.h>')

    # needed for formatted output
    putline('#include <ostream>')

    # Be polite and put everything in a namespace ;3
    putline(f'namespace can_{database["name"]} {{')

    # We'll use this function for getting individual bits off of a
    # 64-bit buffer.
    putline('')
    putline('inline uint64_t read(uint64_t &buffer, uint8_t bits) {')
    putline('  uint64_t res = buffer & ((1 << bits) - 1);')
    putline('  return buffer >>= bits, res;')
    putline('}')

    # And a similar function for writing to a 64-bit buffer.
    putline('')
    putline('inline void write(uint64_t &buffer, uint8_t bits, '
            'uint64_t data) {')
    putline('  buffer <<= bits;')
    putline('  buffer |= data;')
    # putline('  buffer >>= bits;')
    # putline('  buffer |= data << (64 - bits);')
    putline('}')

    putline('enum class MessageDiscriminator {')
    for index, name in enumerate(database['messages'].keys()):
        putline(f'  {name} = {index},')
    putline('};')

    # `bool` is magic and needs a special serializer & deserializer.
    putline('')
    putline('inline bool bool_deserialize(uint64_t buffer) { return buffer; }')
    putline('')
    putline('inline uint64_t serialize(bool data) { return data; }')

    # C++ doesn't let us put structs that haven't been defined yet
    # inside other structs; therefore, we have no choice but to use a
    # topological sort to figure out the order to declare them.
    struct_order = _topological_sort(
        struct_defs.keys(),
        lambda name: struct_defs[name].dependencies(),
    )

    for struct_name in struct_order:
        # Hack
        if struct_name == 'bool':
            continue

        struct_defs[struct_name].serialize_cpp(putline, struct_defs)

    putline(f'}} // namespace can_{database["name"]}')
    putline(f'#endif // {database["name"]}_H')

    return out


T = TypeVar('T')


def _topological_sort(
        nodes: Iterable[T],
        edges: Callable[[T], Iterable[T]]
) -> List[T]:
    """Topological sort of a directed acyclic graph.

    Given a list of nodes in the graph and a function `edges()` that
    takes a node and returns all the nodes it has edges leading to,
    generate a list of all the `nodes` with the property that for any
    nodes N and M, if a path N -> ... -> M exists, then M precedes N
    in the list.

    """
    result: List[T] = []

    def explore(node: T) -> None:
        nonlocal result, nodes, edges
        if node not in result:
            for edge in edges(node):
                explore(edge)
            result.append(node)

    for node in nodes:
        explore(node)

    return result
