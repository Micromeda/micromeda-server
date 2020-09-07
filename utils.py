#!/usr/bin/env python3

"""
Created by: Lee Bergstrand

Description: Utility functions for micromeda-server.

Requirements: - Refer to README
"""

import os

from pygenprop.database_file_parser import parse_genome_properties_flat_file
from pygenprop.results import load_assignment_caches_from_database_with_matches, GenomePropertiesResultsWithMatches
from sqlalchemy import create_engine


def parse_genome_properties_database(genome_properties_flat_file_path):
    """
    Loads the genome properties tree from a file.

    :param genome_properties_flat_file_path: The path to the genome properties flat file.
    :return: A genome properties tree object.
    """
    sanitized_path = sanitize_cli_path(genome_properties_flat_file_path)
    with open(sanitized_path, encoding="utf-8") as genome_properties_file:
        genome_properties_tree = parse_genome_properties_flat_file(genome_properties_file)
    return genome_properties_tree


def extract_results_from_micromeda_file(micromeda_file_path, genome_properties_tree):
    """
    Loads the micromeda file into the app.

    :param micromeda_file_path: The file path to the genome properties file.
    :param genome_properties_tree: The genome properties tree.
    :return: A genome properties results object.
    """
    sanitized_path = sanitize_cli_path(micromeda_file_path)
    engine = create_engine('sqlite:////' + sanitized_path)
    caches = load_assignment_caches_from_database_with_matches(engine)
    results = GenomePropertiesResultsWithMatches(*caches, properties_tree=genome_properties_tree)
    return results


def allowed_file(filename):
    """
    Checks that the uploaded file's extension is allowed.

    :param filename: The uploaded file's name.
    :return: True if the file name has a micro, sqlite, or sqlite3 file extension.
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'micro', 'sqlite', 'sqlite3'}


def sanitize_cli_path(cli_path):
    """
    Performs expansion of '~' and shell variables such as "$HOME" into absolute paths.

    :param cli_path: The path to expand
    :return: An expanded path.
    """
    return os.path.abspath(os.path.expanduser(os.path.expandvars(cli_path)))
