"""
Tests for the CLI module.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from pybindlib.cli import parse_arguments, run_generation_pipeline, main
from pybindlib.pkgconfig import PkgConfigResult


def test_parse_arguments_minimal():
    """Test parsing minimal required arguments."""
    with patch('sys.argv', ['pybindlib', '/path/to/library.so']):
        args = parse_arguments()
        assert args.library_paths == ['/path/to/library.so']
        assert not args.verbose
        assert not args.no_color
        assert not args.skip_typedefs
        assert not args.skip_progress
        assert args.output is None
        assert args.headers is None
        assert args.modules is None
        assert args.include_paths is None
        assert args.pkgconfig is None


def test_parse_arguments_pkgconfig():
    """Test parsing pkgconfig argument."""
    with patch('sys.argv', ['pybindlib', '--pkgconfig', 'freerdp3']):
        args = parse_arguments()
        assert args.pkgconfig == 'freerdp3'
        assert args.library_paths == []  # Now optional when using pkgconfig


def test_parse_arguments_pkgconfig_with_headers():
    """Test parsing pkgconfig with headers argument."""
    with patch('sys.argv', [
        'pybindlib',
        '--pkgconfig', 'freerdp3',
        '--headers', '/usr/include/freerdp3/freerdp.h'
    ]):
        args = parse_arguments()
        assert args.pkgconfig == 'freerdp3'
        assert args.headers == ['/usr/include/freerdp3/freerdp.h']
        assert args.library_paths == []


def test_parse_arguments_missing_library():
    """Test error when required library argument is missing."""
    with patch('sys.argv', ['pybindlib']):
        with pytest.raises(SystemExit):
            parse_arguments()


@pytest.fixture
def mock_pkgconfig():
    """Mock PkgConfig for testing."""
    with patch('pybindlib.cli.PkgConfig') as mock:
        instance = mock.return_value
        result = PkgConfigResult(
            libraries={'freerdp3'},
            include_dirs={'/usr/include/freerdp3'},
            cflags='-I/usr/include/freerdp3',
            libs='-L/usr/lib64 -lfreerdp3'
        )
        instance.query.return_value = result
        yield instance


def test_run_generation_pipeline_pkgconfig(mock_pkgconfig, temp_dir):
    """Test pkgconfig integration in run_generation_pipeline."""
    # Create mock library file that pkg-config should find
    lib_path = os.path.join(temp_dir, 'libfreerdp3.so')
    with open(lib_path, 'wb') as f:
        f.write(b'\x7fELF')  # Minimal ELF header

    args = MagicMock()
    args.pkgconfig = 'freerdp3'
    args.library_paths = []
    args.output = None
    args.no_color = True
    args.verbose = False
    args.skip_progress = True
    args.skip_typedefs = False
    args.headers = None
    args.modules = None
    args.include_paths = None

    with patch('glob.glob', return_value=[lib_path]), \
         patch('pybindlib.cli.load_library_and_debug_info') as mock_load, \
         patch('pybindlib.cli.collect_all_structures_and_typedefs') as mock_collect, \
         patch('pybindlib.cli.generate_python_module') as mock_gen:

        mock_load.return_value = (
            MagicMock(),  # debug_files
            'libfreerdp3.so',  # library_name
            None,  # debug_file_path
            None,  # build_id
            []  # exported_functions
        )
        mock_collect.return_value = ({}, {})  # structures, typedefs

        run_generation_pipeline(args)

        # Verify pkg-config was queried
        mock_pkgconfig.query.assert_called_once_with('freerdp3')

        # Verify include paths were added
        assert args.include_paths == ['/usr/include/freerdp3']

        # Verify library was found and used
        assert args.library_paths == [lib_path]


def test_run_generation_pipeline_pkgconfig_no_library_found(mock_pkgconfig):
    """Test error when pkgconfig can't find library."""
    args = MagicMock()
    args.pkgconfig = 'freerdp3'
    args.library_paths = []
    args.no_color = True
    args.verbose = False

    with patch('glob.glob', return_value=[]), \
         pytest.raises(SystemExit) as exc_info:
        run_generation_pipeline(args)

    assert exc_info.value.code == 1


def test_run_generation_pipeline_pkgconfig_error(mock_pkgconfig):
    """Test error when pkgconfig query fails."""
    args = MagicMock()
    args.pkgconfig = 'freerdp3'
    args.library_paths = []
    args.no_color = True
    args.verbose = False

    mock_pkgconfig.query.side_effect = Exception("pkg-config error")

    with pytest.raises(SystemExit) as exc_info:
        run_generation_pipeline(args)

    assert exc_info.value.code == 1


def test_parse_arguments_full():
    """Test parsing all possible arguments."""
    test_args = [
        'pybindlib',
        '--verbose',
        '--no-color',
        '--skip-typedefs',
        '--skip-progress',
        '--output', 'output.py',
        '--headers', 'header1.h', 'header2.h',
        '--modules', 'mod1', 'mod2',
        '-I', '/include/path1',
        '-I', '/include/path2',
        '/path/to/library.so'
    ]

    with patch('sys.argv', test_args):
        args = parse_arguments()
        assert args.library_paths == ['/path/to/library.so']
        assert args.verbose
        assert args.no_color
        assert args.skip_typedefs
        assert args.skip_progress
        assert args.output == 'output.py'
        assert args.headers == ['header1.h', 'header2.h']
        assert args.modules == ['mod1', 'mod2']
        assert args.include_paths == ['/include/path1', '/include/path2']


@pytest.mark.parametrize('output_path,expected', [
    ('output.py', 'output.py'),
    ('output/', 'output/libtest_so.py'),
    ('path/to/output/', 'path/to/output/libtest_so.py'),
])
def test_run_generation_pipeline_output_handling(output_path, expected, temp_dir):
    """Test output path handling in run_generation_pipeline for a single library."""
    args = MagicMock()
    single_lib_path = os.path.join(temp_dir, 'libtest.so')
    args.library_paths = [single_lib_path]
    args.output = output_path
    args.no_color = True
    args.verbose = False
    args.skip_progress = True
    args.skip_typedefs = False
    args.headers = None
    args.modules = None
    args.include_paths = None
    args.pkgconfig = None

    # Create dummy library file
    with open(single_lib_path, 'wb') as f:
        f.write(b'\x7fELF')  # Minimal ELF header

    with patch('pybindlib.cli.load_library_and_debug_info') as mock_load:
        mock_load.return_value = (
            MagicMock(),  # debug_files
            'libtest.so',  # library_name
            None,  # debug_file_path
            None,  # build_id
            []  # exported_functions
        )

        with patch('pybindlib.cli.collect_all_structures_and_typedefs') as mock_collect:
            mock_collect.return_value = ({}, {})  # structures, typedefs

            with patch('pybindlib.cli.generate_python_module') as mock_gen:
                run_generation_pipeline(args)

                # Verify output directory was created if needed
                if '/' in output_path:
                    assert os.path.isdir(os.path.dirname(expected))

                # Verify generate was called with expected output filename
                called_output = mock_gen.call_args.args[0]
                assert called_output.endswith(expected)


def test_run_generation_pipeline_multiple_libraries_output_dir(temp_dir):
    """When multiple libraries are provided, --output must be a directory and we emit one file per library."""
    args = MagicMock()
    lib1 = os.path.join(temp_dir, 'libone.so')
    lib2 = os.path.join(temp_dir, 'libtwo.so')
    args.library_paths = [lib1, lib2]
    args.output = os.path.join(temp_dir, 'out/')
    args.no_color = True
    args.verbose = False
    args.skip_progress = True
    args.skip_typedefs = False
    args.headers = None
    args.modules = None
    args.include_paths = None
    args.pkgconfig = None

    # Create dummy library files
    for p in [lib1, lib2]:
        with open(p, 'wb') as f:
            f.write(b'\x7fELF')

    with patch('pybindlib.cli.load_library_and_debug_info') as mock_load:
        # Vary library_name for each call
        mock_load.side_effect = [
            (MagicMock(), 'libone.so', None, None, []),
            (MagicMock(), 'libtwo.so', None, None, []),
        ]
        with patch('pybindlib.cli.collect_all_structures_and_typedefs') as mock_collect:
            mock_collect.return_value = ({}, {})
            with patch('pybindlib.cli.generate_python_module') as mock_gen:
                run_generation_pipeline(args)

                # Verify output directory was created
                assert os.path.isdir(os.path.join(temp_dir, 'out'))

                # Verify generate was called for each library
                called_outputs = [call.args[0] for call in mock_gen.call_args_list]
                assert len(called_outputs) == 2
                assert any(name.endswith('out/libone_so.py')
                         for name in called_outputs)
                assert any(name.endswith('out/libtwo_so.py')
                         for name in called_outputs)


def test_main_keyboard_interrupt():
    """Test handling of KeyboardInterrupt in main()."""
    with patch('pybindlib.cli.parse_arguments', side_effect=KeyboardInterrupt):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1


def test_main_general_exception():
    """Test handling of general exceptions in main()."""
    with patch('pybindlib.cli.parse_arguments', side_effect=Exception('Test error')):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
