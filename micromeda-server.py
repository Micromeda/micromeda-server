#!/usr/bin/env python3

"""
Created by: Lee Bergstrand

Description: The server side implementation for Micromeda.

Requirements: - Refer to README
"""

import argparse
import io
import os

import redis
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

from utils import parse_genome_properties_database, extract_results_from_micromeda_file, allowed_file, sanitize_cli_path
from cache import cache_result, get_result_cached_or_default

try:
    redis_url = os.environ['REDIS_URL']
except KeyError:
    REDIS_CACHE = redis.Redis()  # Attempt to use localhost redis with default parameters.
else:
    REDIS_CACHE = redis.from_url(redis_url)


def create_app(config):
    """
    Creates a flask app for the micromeda-server.

    :param config: A configuration dictionary containing info required by the app.
    :return: The app object.
    """
    flask_app = Flask(__name__)
    CORS(flask_app, supports_credentials=True)

    properties_tree = parse_genome_properties_database(config.input_genome_properties_flat_file)

    flask_app.secret_key = config.secret_key
    flask_app.config['UPLOAD_FOLDER'] = sanitize_cli_path(config.uploads_folder)
    flask_app.config['PROPERTIES_TREE'] = properties_tree
    flask_app.config['MAX_CONTENT_LENGTH'] = 110 * 1000 * 1000

    # Cache TTL from CLI is in minutes. We convert it to seconds.
    flask_app.config['CACHE_TTL'] = 60 * config.results_save_time

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

            result_ttl = flask_app.config['CACHE_TTL']
            flask_app.logger.info("Caching micromeda file for {} seconds".format(result_ttl))
            result_key = cache_result(result, REDIS_CACHE, cache_ttl=result_ttl)
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
                genome_property_info = genome_property.to_json(as_dict=True, add_supports=True)

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
                        genome_property_info[genome_property.id] = genome_property.to_json(as_dict=True,
                                                                                           add_supports=True)
        else:
            genome_property_info = {genome_property.id: genome_property.to_json(as_dict=True, add_supports=True) for
                                    genome_property in tree}
        return jsonify(genome_property_info)

    @flask_app.route('/fasta/<string:property_id>/<int:step_number>', methods=['GET'])
    def get_fasta(property_id, step_number):
        """
        Sends a FASTA file to the user containing proteins that support a step.

        :param property_id: The identifier of the genome property.
        :param step_number: The step number of the step.
        :return: A FASTA file encoding for a given property step.
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


if __name__ == '__main__':
    cli_title = """Parses genome properties assignment files and writes their assignments to JSON."""

    parser = argparse.ArgumentParser(description=cli_title)
    parser.add_argument("-p", "--port", action="store", metavar='PORT', default=5000, type=int,
                        help='The port on the server for which micromeda-server shall run on.')

    parser.add_argument("-a", "--host_ip", action="store", metavar='HOST', default='0.0.0.0', type=str,
                        help='The IP address of the server for which micromeda-server shall run on.')

    parser.add_argument('-d', '--input_genome_properties_flat_file', metavar='DB', required=True,
                        help='The path to the genome properties database flat file.')

    parser.add_argument('-k', '--secret_key', metavar='KEY', type=str, default=os.urandom(24),
                        help='The secret key for the micromeda-server.')

    parser.add_argument('-i', '--input_genome_properties_assignment_file', metavar='ASSIGN', default=None,
                        help='The path to micromeda file.')

    parser.add_argument('-u', '--uploads_folder', metavar='UP', default='./',
                        help='The path to a folder for FLASK uploads.')

    parser.add_argument('-t', '--results_save_time', metavar='UP', default=360,
                        help='Time, in minutes, that micromeda file results are saved.')

    parser.add_argument("--debug", action="store_true")

    cli_args = parser.parse_args()

    app = create_app(config=cli_args)
    app.run(host=cli_args.host_ip, port=cli_args.port, debug=cli_args.debug)
