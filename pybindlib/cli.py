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
from .pkgconfig import PkgConfig
from .preprocessor import parse_function_pointer_typedefs, process_headers


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="pybindlib",
        description="Generate Python ctypes bindings from shared libraries",
        epilog="""
Examples:
  # Using explicit library path:
  %(prog)s /usr/lib/libfreerdp.so.3
  %(prog)s --verbose /usr/lib/debug/usr/lib/libfreerdp.so.3.debug

  # Using pkg-config to find library and include paths:
  %(prog)s --pkgconfig freerdp3 --headers freerdp/freerdp.h
  %(prog)s --pkgconfig gtk4 --headers gtk/gtk.h

  # Output options:
  %(prog)s --output my_bindings.py /path/to/library.so
  %(prog)s --output ./output/ /path/to/library.so
  %(prog)s --output output/bindings.py /path/to/library.so
  %(prog)s ./libone.so ./libtwo.so
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "library_paths",
        metavar="LIBRARY_PATH",
        nargs="*",
        help="Path(s) to the shared library or debug file to analyze",
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

    parser.add_argument(
        "--pkgconfig",
        metavar="PACKAGE",
        help="""Use pkg-config to find library and include paths for the given package (e.g., freerdp3, gtk4).
If no explicit library paths are provided, will attempt to find the library files automatically.
Use with --headers to specify which header files to process.""",
    )

    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")

    args = parser.parse_args()

    # Validate that we have library paths if not using pkgconfig
    if not args.pkgconfig and not args.library_paths:
        parser.error("At least one library path is required when not using --pkgconfig")

    return args


def run_generation_pipeline(args: argparse.Namespace) -> None:
    """
    Execute the complete bindings generation pipeline.

    Args:
        args: Parsed command line arguments
    """
    use_color = not args.no_color

    # Set up logging
    logger = setup_logging(verbose=args.verbose, use_color=use_color)

    print_banner("pybindlib — Generate ctypes Python bindings", use_color=use_color)

    # Query pkg-config if requested
    library_paths = list(args.library_paths)  # Convert to list to allow modification
    if args.pkgconfig:
        print_section_header("Querying pkg-config", use_color=use_color)
        try:
            pkg_config = PkgConfig()
            pkg_info = pkg_config.query(args.pkgconfig)
            logger.info(f"Found package {args.pkgconfig}")

            # Add include paths from pkg-config
            if not args.include_paths:
                args.include_paths = []
            args.include_paths.extend(pkg_info.get_include_dirs())
            logger.info(f"Added {len(pkg_info.get_include_dirs())} include paths from pkg-config")

            if args.verbose:
                for path in pkg_info.get_include_dirs():
                    logger.debug(f"Include path: {path}")

            # If no library paths provided, try to find them from pkg-config
            if not library_paths:
                # pkg-config --libs returns -L/path/to/lib -lfoo, we need to combine them
                lib_dirs = pkg_info.get_library_dirs()
                lib_names = pkg_info.get_library_names()

                for lib_name in lib_names:
                    found = False
                    for lib_dir in lib_dirs:
                        # Try common library name patterns
                        patterns = [
                            f"lib{lib_name}.so",
                            f"lib{lib_name}.so.*",
                            f"lib{lib_name}-*.so",
                        ]
                        for pattern in patterns:
                            import glob
                            matches = glob.glob(os.path.join(lib_dir, pattern))
                            if matches:
                                # Sort to get the highest version number if multiple matches
                                matches.sort()
                                library_paths.append(matches[-1])
                                found = True
                                logger.info(f"Found library: {matches[-1]}")
                                break
                        if found:
                            break

                    if not found:
                        logger.warning(f"Could not find library for {lib_name}")

        except Exception as e:
            logger.error(f"Failed to query pkg-config: {e}")
            sys.exit(1)

    # Ensure we have at least one library path
    if not library_paths:
        logger.error("No library paths provided and could not find any via pkg-config")
        sys.exit(1)

    # Update args.library_paths for the rest of the pipeline
    args.library_paths = library_paths

    # Preprocess headers once if provided
    macros_from_headers: dict[str, str] = {}
    function_pointer_typedefs_from_headers: set[str] = set()
    if args.headers:
        print_section_header("Processing Headers", use_color=use_color)
        logger.info(f"Processing {len(args.headers)} header files...")
        macros_from_headers = process_headers(
            args.headers, args.include_paths, args.modules
        ) or {}
        logger.info(f"Extracted {len(macros_from_headers)} macro definitions")
        if not args.skip_typedefs:
            logger.debug(
                "Scanning headers for function-pointer typedefs to supplement DWARF typedefs"
            )
            function_pointer_typedefs_from_headers = set(
                parse_function_pointer_typedefs(args.headers)
            )

    # Determine output directory behavior for multiple libraries
    multiple_libraries = len(getattr(args, "library_paths", []) or []) > 1
    output_is_directory_for_multiple = False
    output_directory: str | None = None
    if args.output and multiple_libraries:
        # Treat output as directory only; create if necessary
        if os.path.isdir(args.output):
            output_is_directory_for_multiple = True
            output_directory = args.output
        else:
            # If the path ends with a path separator, treat as directory and create
            seps = [os.sep]
            if os.altsep:
                seps.append(os.altsep)
            if any(args.output.endswith(sep) for sep in seps):
                os.makedirs(args.output, exist_ok=True)
                output_is_directory_for_multiple = True
                output_directory = args.output
            else:
                raise ValueError(
                    "When multiple libraries are provided, --output must be a directory (e.g., './out/')."
                )

    # Process each library
    for library_path in args.library_paths:
        print()
        print_section_header("Loading Library", use_color=use_color)
        logger.info(f"Loading library: {library_path}")
        (
            debug_files,
            library_name,
            debug_file_path,
            build_id,
            exported_functions,
        ) = load_library_and_debug_info(library_path)

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
            logger.debug(
                f"Auxiliary file: {debug_files.auxiliary_file.file_path}"
            )

        print()
        print_section_header("Analyzing Debug Information", use_color=use_color)
        all_structures, all_typedefs = collect_all_structures_and_typedefs(
            debug_files, skip_progress=args.skip_progress
        )

        # Filter/augment typedefs
        if args.skip_typedefs:
            all_typedefs = {}
            logger.debug("Skipping typedefs per --skip-typedefs option")
        elif function_pointer_typedefs_from_headers:
            added = 0
            for typedef_name in function_pointer_typedefs_from_headers:
                if typedef_name not in all_typedefs:
                    all_typedefs[typedef_name] = TypedefInfo(
                        representation="c_void_p",
                        quality_score=QualityScore(base_score=4, size_score=1),
                        description="pointer to function type",
                    )
                    added += 1
            logger.debug(
                f"Added {added} function-pointer typedefs from headers"
            )

        # Determine output filename for this library
        if args.output:
            if multiple_libraries and output_is_directory_for_multiple:
                generated_filename = generate_output_filename(
                    library_name, library_path
                )
                output_filename = os.path.join(
                    output_directory, generated_filename
                )  # type: ignore[arg-type]
                logger.debug(
                    f"Output directory (multiple), using: {output_filename}"
                )
            elif os.path.isdir(args.output):
                # If output is a directory, generate filename and place it there
                generated_filename = generate_output_filename(
                    library_name, library_path
                )
                output_filename = os.path.join(args.output, generated_filename)
                logger.debug(
                    f"Output is directory, using: {output_filename}"
                )
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
                        logger.debug(
                            f"Creating parent directories: {parent_dir}"
                        )
                        os.makedirs(parent_dir, exist_ok=True)
        else:
            output_filename = generate_output_filename(
                library_name, library_path
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
            macros_from_headers,
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
