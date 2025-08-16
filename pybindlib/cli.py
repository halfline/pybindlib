"""
Command-line interface for pybindlib.
"""

# Standard library imports
import argparse
import os
import sys

# Local imports
from .debug_info import (
    QualityScore,
    TypedefInfo,
    collect_all_structures_and_typedefs,
    load_library_and_debug_info,
)
from .generator import (
    generate_python_module,
    print_usage_example,
)
from .logging import logger, setup_logging
from .output import (
    print_banner,
    print_file_info,
    print_section_header,
    print_success,
)
from .paths import generate_output_filename, strip_trailing_whitespace_from_file
from .preprocessor import parse_function_pointer_typedefs, process_headers


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="pybindlib",
        description="Generate Python ctypes bindings from shared libraries",
        epilog="""
Examples:
  %(prog)s /usr/lib/libfreerdp.so.3
  %(prog)s --verbose /usr/lib/debug/usr/lib/libfreerdp.so.3.debug
  %(prog)s --output my_bindings.py /path/to/library.so
  %(prog)s --output ./output/ /path/to/library.so
  %(prog)s --output output/bindings.py /path/to/library.so
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "library_path",
        metavar="LIBRARY_PATH",
        help="Path to the shared library or debug file to analyze",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging output",
    )

    parser.add_argument(
        "-o",
        "--output",
        metavar="OUTPUT_PATH",
        help="Output file or directory for generated bindings (default: auto-generated from library name)",
    )

    parser.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )

    parser.add_argument(
        "--skip-typedefs",
        action="store_true",
        help="Generate bindings for structures only, skip typedefs",
    )

    parser.add_argument(
        "--skip-progress",
        action="store_true",
        help="Disable progress animation for scripting environments",
    )

    parser.add_argument(
        "--headers",
        metavar="HEADER_FILE",
        nargs="+",
        help="Header files to parse for macro definitions",
    )

    parser.add_argument(
        "--modules",
        metavar="MODULE",
        nargs="+",
        help="Pre-built modules to reference for constants (e.g., libwinpr3_so_3)",
    )

    parser.add_argument(
        "-I",
        dest="include_paths",
        metavar="INCLUDE_PATH",
        action="append",
        help="Additional include paths for header preprocessing",
    )

    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")

    return parser.parse_args()


def run_generation_pipeline(args: argparse.Namespace) -> None:
    """
    Execute the complete bindings generation pipeline.

    Args:
        args: Parsed command line arguments
    """
    use_color = not args.no_color

    # Set up logging
    logger = setup_logging(verbose=args.verbose, use_color=use_color)

    print_banner(use_color=use_color)

    print_section_header("Loading Library", use_color=use_color)
    logger.info(f"Loading library: {args.library_path}")
    debug_files, library_name, debug_file_path, build_id, exported_functions = (
        load_library_and_debug_info(args.library_path)
    )

    print_file_info("Library name", library_name, use_color=use_color)
    print_file_info("Build ID", build_id or "unknown", use_color=use_color)
    print_file_info("Debug file", debug_file_path, use_color=use_color)

    # Show information about the debug files found
    if debug_files.main_file:
        logger.debug(f"Main debuginfo file: {debug_files.main_file.file_path}")
    if debug_files.has_auxiliary():
        print_file_info(
            "Auxiliary debuginfo file",
            debug_files.auxiliary_file.file_path,
            use_color=use_color,
        )
        logger.debug(f"Auxiliary file: {debug_files.auxiliary_file.file_path}")

    print()
    print_section_header("Analyzing Debug Information", use_color=use_color)
    all_structures, all_typedefs = collect_all_structures_and_typedefs(
        debug_files, skip_progress=args.skip_progress
    )

    # Process header files if provided
    macros = {}
    if args.headers:
        print()
        print_section_header("Processing Headers", use_color=use_color)
        logger.info(f"Processing {len(args.headers)} header files...")
        macros = (
            process_headers(args.headers, args.include_paths, args.modules)
            or {}
        )
        logger.info(f"Extracted {len(macros)} macro definitions")

    # Filter typedefs if requested
    if args.skip_typedefs:
        all_typedefs = {}
        logger.debug("Skipping typedefs per --skip-typedefs option")
    # Best-effort: add function-pointer typedefs discovered from headers as c_void_p
    elif args.headers:
        logger.debug(
            "Scanning headers for function-pointer typedefs to supplement DWARF typedefs"
        )
        fn_typedefs = parse_function_pointer_typedefs(args.headers)
        added = 0
        for typedef_name in fn_typedefs:
            if typedef_name not in all_typedefs:
                all_typedefs[typedef_name] = TypedefInfo(
                    representation="c_void_p",
                    quality_score=QualityScore(base_score=4, size_score=1),
                    description="pointer to function type",
                )
                added += 1
        logger.debug(f"Added {added} function-pointer typedefs from headers")

    # Determine output filename
    if args.output:
        if os.path.isdir(args.output):
            # If output is a directory, generate filename and place it there
            generated_filename = generate_output_filename(
                library_name, args.library_path
            )
            output_filename = os.path.join(args.output, generated_filename)
            logger.debug(f"Output is directory, using: {output_filename}")
        else:
            # If output is a file path (or doesn't exist yet), use it directly
            output_filename = args.output

            # Auto-create parent directories only when path structure is unambiguous:
            # - Path ends with directory separator (e.g., "output/") - clearly a directory
            # - OR path has any directory separators (e.g., "output/file.py", "path/to/file.py")
            # Skip only the ambiguous case: single component with no separators (e.g., "output")
            separators = [os.sep]
            if os.altsep:
                separators.append(os.altsep)

            has_separators = any(sep in output_filename for sep in separators)

            if has_separators:
                parent_dir = os.path.dirname(output_filename)
                if parent_dir and not os.path.exists(parent_dir):
                    logger.debug(f"Creating parent directories: {parent_dir}")
                    os.makedirs(parent_dir, exist_ok=True)
    else:
        output_filename = generate_output_filename(
            library_name, args.library_path
        )

    print()
    print_section_header("Generating Python Module", use_color=use_color)
    logger.info(f"Generating {output_filename}...")
    generate_python_module(
        output_filename,
        library_name,
        build_id,
        all_structures,
        all_typedefs,
        exported_functions,
        macros,
    )

    # Strip any trailing whitespace in the generated file
    strip_trailing_whitespace_from_file(output_filename)

    # Success summary
    print_success(
        f"Successfully generated {output_filename}", use_color=use_color
    )

    # Print usage example with discovered real function and struct names
    print_usage_example(
        debug_files,
        all_structures,
        all_typedefs,
        output_filename,
        use_color=use_color,
    )


def main():
    """Main entry point for the CLI."""
    args = None
    try:
        args = parse_arguments()
        run_generation_pipeline(args)
    except KeyboardInterrupt:
        logger.error("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        if args and args.verbose:
            logger.exception("Detailed error information:")
        sys.exit(1)


if __name__ == "__main__":
    main()
