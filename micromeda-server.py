#!/usr/bin/env python3

"""
Created by: Lee Bergstrand

Description: The server side implementation for Micromeda.

Requirements: - Refer to README
"""

import argparse
import os
from flask import Flask, session, request
from werkzeug.utils import secure_filename
from pygenprop.database_file_parser import parse_genome_properties_flat_file
from pygenprop.results import GenomePropertiesResultsWithMatches
from pygenprop.results import load_assignment_caches_from_database_with_matches
from sqlalchemy import create_engine


def create_app(config):
    app = Flask(__name__)

    properties_tree = parse_genome_properties_database(config.input_genome_properties_flat_file)

    app.secret_key = config.secret_key
    app.config['UPLOAD_FOLDER'] = sanitize_cli_path(config.uploads_folder)
    app.config['PROPERTIES_TREE'] = properties_tree

    if config.input_genome_properties_assignment_file is not None:
        default_results = extract_results_from_micromeda_file(config.input_genome_properties_assignment_file,
                                                              properties_tree)
    else:
        default_results = None

    app.config['DEFAULT_RESULTS'] = default_results

    @app.route('/upload', methods=['GET', 'POST'])
    def upload():
        file = request.files['file']

        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            out_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(out_path)
            result = extract_results_from_micromeda_file(out_path, app.config['PROPERTIES_TREE'])
            os.remove(out_path)

            session['result'] = result

    @app.route('/upload', methods=['GET'])
    def get_tree():
        session_result = session.get('result')
        default_result = app.config['DEFAULT_RESULTS']

        if session_result is not None:
            tree_json = session_result.to_json()
        elif default_result is not None:
            tree_json = default_result.to_json()
        else:
            tree_json = None

        if tree_json:
            response = app.response_class(response=tree_json, status=200, mimetype='application/json')
        else:
            response = app.response_class(response='No tree found.', status=404)

        return response

    return app

def parse_genome_properties_database(genome_properties_flat_file_path):
    sanitized_path = sanitize_cli_path(genome_properties_flat_file_path)
    with open(sanitized_path) as genome_properties_file:
        genome_properties_tree = parse_genome_properties_flat_file(genome_properties_file)
    return genome_properties_tree


def extract_results_from_micromeda_file(micromeda_file_path, genome_properties_tree):
    sanitized_path = sanitize_cli_path(micromeda_file_path)
    engine = create_engine('sqlite:////' + sanitized_path)
    caches = load_assignment_caches_from_database_with_matches(engine)
    results = GenomePropertiesResultsWithMatches(*caches, properties_tree=genome_properties_tree)
    return results

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'micro', 'sqlite', 'sqlite3'}

def sanitize_cli_path(cli_path):
    """
    Performs expansion of '~' and shell variables such as "$HOME" into absolute paths.

    :param cli_path: The path to expand
    :return: An expanded path.
    """
    sanitized_path = path.expanduser(path.expandvars(cli_path))
    return sanitized_path


if __name__ == '__main__':
    cli_title = """Parses genome properties assignment files and writes their assignments to JSON."""

    parser = argparse.ArgumentParser(description=cli_title)
    parser.add_argument("-p", "--port", action="store", metavar='PORT', default=5000, type=int,
                        help='The port on the server for which micromeda-server shall run on.')

    parser.add_argument("-h", "--host", action="store", metavar='HOST', default='0.0.0.0', type=str,
                        help='The IP address of the server for which micromeda-server shall run on.')

    parser.add_argument('-d', '--input_genome_properties_flat_file', metavar='DB', required=True,
                        help='The path to the genome properties database flat file.')

    parser.add_argument('-k', '--secret_key', metavar='KEY', required=True, type=str,
                        help='The secret key for the micromeda-server.')

    parser.add_argument('-i', '--input_genome_properties_assignment_file', metavar='ASSIGN', default=None,
                        help='The path to micromeda file.')

    parser.add_argument('-u', '--uploads_folder', metavar='UP', default='./',
                        help='The path to a folder for FLASK uploads.')

    parser.add_argument("--debug", action="store_true")

    cli_args = parser.parse_args()

    app = create_app(config=cli_args)
    app.run(host='0.0.0.0', port=cli_args.port, debug=cli_args.debug)
