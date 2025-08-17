"""
Tests for the CLI module.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from pybindlib.cli import parse_arguments, run_generation_pipeline, main


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


def test_parse_arguments_missing_library():
    """Test error when required library argument is missing."""
    with patch('sys.argv', ['pybindlib']):
        with pytest.raises(SystemExit):
            parse_arguments()


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
                # Ensure directory exists and two files generated with expected names
                assert os.path.isdir(args.output)
                called_outputs = [call.args[0] for call in mock_gen.call_args_list]
                assert any(name.endswith('out/libone_so.py') for name in called_outputs)
                assert any(name.endswith('out/libtwo_so.py') for name in called_outputs)


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
