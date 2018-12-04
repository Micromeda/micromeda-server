#!/usr/bin/env python3

"""
Created by: Lee Bergstrand

Description: The server side implementation for Micromeda.

Requirements: - Refer to README
"""

from flask import Flask, request
from flask_restful import Resource, Api
from pygenprop.flat_file_parser import parse_genome_property_file

app = Flask(__name__)
api = Api(app)

with open('testing/test_files/genomeProperties.txt') as genome_properties_file:
    genome_properties_tree = parse_genome_property_file(genome_properties_file)


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
                            genome_property_info[genome_property.id] = self.generate_genome_property_info_json(genome_property)
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
