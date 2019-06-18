#!/usr/bin/env python3

"""
Created by: Lee Bergstrand

Description: The server side implementation for Micromeda.

Requirements: - Refer to README
"""

import argparse
import io
import os
import uuid

import pandas as pd
import redis
from flask import Flask, request, jsonify, send_file
from pygenprop.database_file_parser import parse_genome_properties_flat_file
from pygenprop.results import GenomePropertiesResultsWithMatches
from pygenprop.results import load_assignment_caches_from_database_with_matches
from sqlalchemy import create_engine
from werkzeug.utils import secure_filename

REDIS_CACHE = redis.Redis(host='localhost', port=6379, db=0)  # TODO: Add these parameters from args or config file.


def create_app(config):
    """
    Creates a flask app for the micromeda-server.

    :param config: A configuration dictionary containing info required by the app.
    :return: The app object.
    """
    flask_app = Flask(__name__)

    properties_tree = parse_genome_properties_database(config.input_genome_properties_flat_file)

    flask_app.secret_key = config.secret_key
    flask_app.config['UPLOAD_FOLDER'] = sanitize_cli_path(config.uploads_folder)
    flask_app.config['PROPERTIES_TREE'] = properties_tree

    if config.input_genome_properties_assignment_file is not None:
        default_results = extract_results_from_micromeda_file(config.input_genome_properties_assignment_file,
                                                              properties_tree)
    else:
        default_results = None

    flask_app.config['DEFAULT_RESULTS'] = default_results

    @flask_app.route('/upload', methods=['GET', 'POST'])
    def upload():
        """
        An endpoint for uploading micromeda files.
        """
        global REDIS_CACHE

        file = request.files['file']

        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            out_path = os.path.join(flask_app.config['UPLOAD_FOLDER'], filename)
            file.save(out_path)
            result = extract_results_from_micromeda_file(out_path, flask_app.config['PROPERTIES_TREE'])
            os.remove(out_path)

            result_key = cache_result(result, REDIS_CACHE)
            response = jsonify({'result_key': result_key})
        else:
            response = flask_app.response_class(response='Upload failed', status=404)

        return response

    @flask_app.route('/genome_properties_tree', methods=['GET'])
    def get_tree():
        """
        An endpoint for getting the genome properties tree from micromeda-server.

        :return: The genome properties tree, with assignments, as JSON.
        """
        global REDIS_CACHE
        result = get_result_cached_or_default(redis_cache=REDIS_CACHE,
                                              properties_tree=flask_app.config['PROPERTIES_TREE'],
                                              results_key=request.args.get('result_key'),
                                              default_results=flask_app.config['DEFAULT_RESULTS'])
        if result is not None:
            response = flask_app.response_class(response=(result.to_json()), status=200, mimetype='application/json')
        else:
            response = flask_app.response_class(response='No tree found.', status=404)

        return response

    @flask_app.route('/genome_properties/<string:property_id>')
    def get_single_genome_property_info(property_id=None):
        """
        Gathers information for a specific genome property.

        :param property_id: The genome property identifier of the property for which we are grabbing information.
        :return: The info about the genome property.
        """
        tree = flask_app.config['PROPERTIES_TREE']

        genome_property_info = {}
        if property_id:
            genome_property = tree[property_id]
            if genome_property:
                genome_property_info = generate_genome_property_info_json(genome_property)

        return jsonify(genome_property_info)

    @flask_app.route('/genome_properties', methods=['GET'])
    def get_multiple_genome_property_info():
        """
        Gathers information for multiple genome properties.

        :return: The info about the genome property.
        """
        tree = flask_app.config['PROPERTIES_TREE']
        url_args = request.args
        genome_property_info = {}
        if url_args:
            for parameter, property_id in url_args.items():
                if 'gp_id' in parameter:
                    genome_property = tree[property_id]
                    if genome_property:
                        genome_property_info[genome_property.id] = generate_genome_property_info_json(
                            genome_property)
        else:
            genome_property_info = {genome_property.id: generate_genome_property_info_json(genome_property) for
                                    genome_property in tree}
        return jsonify(genome_property_info)

    @flask_app.route('/fasta/<string:property_id>/<int:step_number>', methods=['GET'])
    def get_fasta(property_id, step_number):
        """
        Sends a FASTA file to the user containing proteins that support a step.

        :param property_id: The identifier of the genome property.
        :param step_number: The step number of the step.
        :return: A FASTA file encoding for
        """
        global REDIS_CACHE
        result = get_result_cached_or_default(redis_cache=REDIS_CACHE,
                                              properties_tree=flask_app.config['DEFAULT_RESULTS'],
                                              results_key=request.args.get('result_key'),
                                              default_results=flask_app.config['DEFAULT_RESULTS'])

        text_stream = io.StringIO()
        binary_stream = io.BytesIO()

        all_result = request.args.get('all')
        if all_result == 'true':
            top = False
            file_designator = 'all'
        else:
            top = True
            file_designator = 'top'

        if result is not None:
            result.write_supporting_proteins_for_step_fasta(text_stream, property_id, step_number, top=top)
            binary_stream.write(text_stream.getvalue().encode())
            binary_stream.seek(0)

        text_stream.close()

        return send_file(
            binary_stream,
            as_attachment=True,
            attachment_filename=property_id + '_' + str(step_number) + '_' + file_designator + '.faa',
            mimetype='text/x-fasta'
        )

    return flask_app


def generate_genome_property_info_json(genome_property):
    """
    Generates a json dict containing information about a genome property.

    :param genome_property: The input genome property.
    :return:
    """
    property_name = genome_property.name
    description = genome_property.description
    literature = [reference.pubmed_id for reference in genome_property.references]

    databases_info = {}
    databases = genome_property.databases

    if databases:
        for database_reference in databases:
            database_name = database_reference.database_name
            identifiers = database_reference.record_ids

            if database_name in databases_info.keys():
                databases_info[database_name].append(identifiers)
            else:
                databases_info[database_name] = identifiers

    return {'name': property_name, 'description': description, 'pubmed': literature, 'databases': databases_info}


def parse_genome_properties_database(genome_properties_flat_file_path):
    """
    Loads the genome properties tree from a file.

    :param genome_properties_flat_file_path: The path to the genome properties flat file.
    :return: A genome properties tree object.
    """
    sanitized_path = sanitize_cli_path(genome_properties_flat_file_path)
    with open(sanitized_path) as genome_properties_file:
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


class GenomePropertiesResultsWithMatchesCached(GenomePropertiesResultsWithMatches):

    def __init__(self, property_results_frame, step_results_frame, step_matches_frame, properties_tree):
        self.property_results = property_results_frame
        self.step_results = step_results_frame
        self.step_matches = step_matches_frame
        self.tree = properties_tree
        self.sample_names = self.property_results.columns.tolist()


def cache_result(result, redis_cache):
    results_frames = [result.property_results,
                      result.step_results,
                      result.step_matches]

    key = uuid.uuid4().hex
    data = pd.to_msgpack(None, *results_frames)
    redis_cache.set(key, data)
    return key


def get_result_cached_or_default(redis_cache, properties_tree, results_key=None, default_results=None):
    if results_key:
        result = get_result_from_cache(results_key, redis_cache, properties_tree)
    elif default_results is not None:
        result = default_results
    else:
        result = None

    return result


def get_result_from_cache(key, redis_cache, properties_tree):
    cached_results = redis_cache.get(key)
    if cached_results is not None:
        stored_dataframes = pd.read_msgpack(cached_results)
        property_results = stored_dataframes[0]
        step_results = stored_dataframes[1]
        step_matches = stored_dataframes[2]

        result = GenomePropertiesResultsWithMatchesCached(property_results, step_results, step_matches, properties_tree)
    else:
        result = None

    return result


if __name__ == '__main__':
    cli_title = """Parses genome properties assignment files and writes their assignments to JSON."""

    parser = argparse.ArgumentParser(description=cli_title)
    parser.add_argument("-p", "--port", action="store", metavar='PORT', default=5000, type=int,
                        help='The port on the server for which micromeda-server shall run on.')

    parser.add_argument("-a", "--host_ip", action="store", metavar='HOST', default='0.0.0.0', type=str,
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
    app.run(host=cli_args.host_ip, port=cli_args.port, debug=cli_args.debug)
