#!/usr/bin/env python3

"""
Created by: Lee Bergstrand

Description: The server side implementation for Micromeda.

Requirements: - Refer to README
"""
import os

from flask import Flask, request
from flask_restful import Resource, Api
from sqlalchemy import create_engine
from pygenprop.results import load_assignment_caches_from_database_with_matches
from pygenprop.results import GenomePropertiesResultsWithMatches
from pygenprop.database_file_parser import parse_genome_properties_flat_file
from werkzeug.utils import secure_filename

app = Flask(__name__)
api = Api(app)

properties_path = '/Users/lee/Dropbox/RandD/Repositories/micromeda-server/testing/test_files/genomeProperties.txt'
with open(properties_path) as genome_properties_file:
    genome_properties_tree = parse_genome_properties_flat_file(genome_properties_file)

path_sqlite_file = '/Users/lee/Dropbox/RandD/Repositories/micromeda-server/testing/test_files/data.micro'
engine_url = 'sqlite:////' + path_sqlite_file
engine = create_engine(engine_url)

results = GenomePropertiesResultsWithMatches(*load_assignment_caches_from_database_with_matches(engine),
                                             properties_tree=genome_properties_tree)
tree_json = results.to_json()

uploads = []



class GenomePropertyTreeResource(Resource):

    def get(self):
        response = app.response_class(
            response=tree_json,
            status=200,
            mimetype='application/json'
        )
        return response

class GenomePropertyResource(Resource):
    """A rest resource for individual genome properties."""

    def get(self, property_id=None):

        genome_property_info = {}

        if property_id:
            genome_property = genome_properties_tree[property_id]
            if genome_property:
                genome_property_info = self.generate_genome_property_info_json(genome_property)
        else:
            url_args = request.args
            if url_args:
                for parameter, property_id in url_args.items():
                    if 'gp_id' in parameter:
                        genome_property = genome_properties_tree[property_id]
                        if genome_property:
                            genome_property_info[genome_property.id] = self.generate_genome_property_info_json(
                                genome_property)
            else:
                genome_property_info = {genome_property.id: self.generate_genome_property_info_json(genome_property) for
                                        genome_property in genome_properties_tree}

        return genome_property_info

    @staticmethod
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

        return {'name': property_name,
                'description': description,
                'pubmed': literature,
                'databases': databases_info}


api.add_resource(GenomePropertyResource, '/genome_properties/<string:property_id>', '/genome_properties')
api.add_resource(GenomePropertyTreeResource, '/genome_properties_tree')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
