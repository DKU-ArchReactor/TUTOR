"""Read ELF DWARF locations for actual instruction PCs without executing ELF."""
from bisect import bisect_left
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from elftools.elf.elffile import ELFFile
from .events import obj, pc


def enrich_mapping(result: dict, elf_bytes: bytes, source_file: str = 'source.c') -> dict:
    if not 0 < len(elf_bytes) <= 256 * 1024:
        raise ValueError('ELF must be at most 256 KiB')
    expected = obj(result.get('program')).get('fingerprint')
    if expected and expected != sha256(elf_bytes).hexdigest():
        raise ValueError('ELF fingerprint does not match the simulation')
    output = deepcopy(result)
    program = output.setdefault('program', {})
    original = obj(program.get('code_mapping')) or {item['pc']: item for item in program.get('instructions', []) if isinstance(item, dict) and item.get('pc')}
    mapping = {pc(key): {**value, 'source_line': None, 'source_file': None, 'source_column': None, 'mapping_basis': 'elf_dwarf'} for key, value in original.items() if pc(key) and isinstance(value, dict)}
    addresses = sorted(int(key, 16) for key in mapping)
    selected_name = PurePosixPath(source_file.replace('\\', '/')).name
    try:
        elf = ELFFile(BytesIO(elf_bytes))
        if elf['e_machine'] != 'EM_RISCV' or elf.elfclass != 32:
            raise ValueError('Expected an RV32 ELF')
        # Compressed debug sections are rejected rather than expanded without a size bound.
        if any(section.name.startswith('.zdebug') or section['sh_flags'] & 0x800 for section in elf.iter_sections()):
            raise ValueError('Compressed debug sections are not supported')
        symbols = elf.get_section_by_name('.symtab')
        if symbols:
            for symbol in symbols.iter_symbols():
                if symbol['st_info']['type'] != 'STT_FUNC' or not symbol['st_size']:
                    continue
                start, end = symbol['st_value'], symbol['st_value'] + symbol['st_size']
                for address in addresses[bisect_left(addresses, start):bisect_left(addresses, end)]:
                    mapping[f'0x{address:08X}']['function'] = symbol.name
        if elf.has_dwarf_info():
            dwarf = elf.get_dwarf_info()
            for unit in dwarf.iter_CUs():
                lines = dwarf.line_program_for_CU(unit)
                if lines is None:
                    continue
                files = lines.header['file_entry']
                previous = None
                for entry in lines.get_entries():
                    current = entry.state
                    if current is None:
                        continue
                    if previous is not None and not previous.end_sequence and current.address > previous.address and previous.line:
                        # DWARF 2-4 file numbers are 1-based; DWARF 5 file numbers are 0-based.
                        file_index = previous.file if lines.header.version >= 5 else previous.file - 1
                        if 0 <= file_index < len(files):
                            raw_name = files[file_index].name
                            name = raw_name.decode('utf-8', 'replace') if isinstance(raw_name, bytes) else str(raw_name)
                            base_name = PurePosixPath(name.replace('\\', '/')).name
                            for address in addresses[bisect_left(addresses, previous.address):bisect_left(addresses, current.address)]:
                                record = mapping[f'0x{address:08X}']
                                record.update({'source_file': name, 'source_column': previous.column or None,
                                               'source_line': previous.line if base_name == selected_name else None,
                                               'external_source_line': previous.line if base_name != selected_name else None})
                    previous = current
    except ValueError:
        raise
    except Exception as error:
        raise ValueError('Cannot read ELF debug metadata') from error
    program['code_mapping'] = mapping
    return output
