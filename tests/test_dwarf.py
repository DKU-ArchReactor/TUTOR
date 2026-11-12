from copy import deepcopy
from types import SimpleNamespace
import pytest
from archreactor_tutor import dwarf


@pytest.mark.parametrize('version', [4, 5])
def test_file_index_and_zero_length_ranges_do_not_map_runtime_as_user_c(monkeypatch, version):
    class Header(dict):
        pass
    header = Header(file_entry=[SimpleNamespace(name=b'start.S'), SimpleNamespace(name=b'source.c')])
    header.version = version
    offset = 0 if version == 5 else 1
    states = [
        SimpleNamespace(address=0x10000, line=1, column=0, file=offset, end_sequence=False),
        SimpleNamespace(address=0x10004, line=1, column=2, file=1 + offset, end_sequence=False),
        # Same-address entries replace one another; no fabricated 4-byte interval.
        SimpleNamespace(address=0x10004, line=2, column=4, file=1 + offset, end_sequence=False),
        SimpleNamespace(address=0x10008, line=3, column=0, file=1 + offset, end_sequence=True),
    ]
    class Lines:
        def __init__(self): self.header = header
        def get_entries(self): return [SimpleNamespace(state=state) for state in states]
    class Info:
        def iter_CUs(self): return [None]
        def line_program_for_CU(self, unit): return Lines()
    class Elf:
        elfclass = 32
        def __getitem__(self, key): return 'EM_RISCV'
        def iter_sections(self): return []
        def get_section_by_name(self, name): return None
        def has_dwarf_info(self): return True
        def get_dwarf_info(self): return Info()
    monkeypatch.setattr(dwarf, 'ELFFile', lambda stream: Elf())
    result = {'program': {'code_mapping': {'0x10000': {'assembly': 'auipc ra,0', 'source_line': 1}, '0x10004': {'assembly': 'addi a0,zero,1'}}}}
    before = deepcopy(result)
    enriched = dwarf.enrich_mapping(result, b'fixture')
    assert result == before
    assert enriched['program']['code_mapping']['0x00010000']['source_line'] is None
    user = enriched['program']['code_mapping']['0x00010004']
    assert user['source_line'] == 2 and user['source_column'] == 4 and user['source_file'] == 'source.c'


def test_mismatched_elf_fingerprint_is_rejected():
    with pytest.raises(ValueError, match='fingerprint'):
        dwarf.enrich_mapping({'program': {'fingerprint': 'different-program'}}, b'elf')


def test_large_elf_is_rejected_before_parsing():
    with pytest.raises(ValueError, match='256 KiB'):
        dwarf.enrich_mapping({}, b'x' * (256 * 1024 + 1))
