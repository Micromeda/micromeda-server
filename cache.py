#!/usr/bin/env python3

"""
Created by: Lee Bergstrand

Description: Caching functions for micromeda-server.

Requirements: - Refer to README
"""
import uuid

from pygenprop.results import GenomePropertiesResultsWithMatches, load_results_from_serialization


def cache_result(result: GenomePropertiesResultsWithMatches, redis_cache, cache_ttl=3600):
    """
    Takes a GenomePropertiesResultsWithMatches, serializes it, and stores it in a redis cache.

    :param cache_ttl: Number of seconds that the result should stay in the cache in seconds.
    :param result: A GenomePropertiesResultsWithMatches object
    :param redis_cache: A object representing a Redis cache
    :return: The hexadecimal key used to identify the serialized results in the cache
    """
    key = uuid.uuid4().hex
    data = result.to_serialization()
    redis_cache.set(key, data, ex=cache_ttl)
    return key


def get_result_cached_or_default(redis_cache, properties_tree, results_key=None, default_results=None):
    """
    Retrieved a cached and serialized GenomePropertiesResultsWithMatches from the cache and reconstitutes it into a
    GenomePropertiesResultsWithMatches that can be used.

    :param redis_cache: A object representing a Redis cache
    :param properties_tree: A GenomePropertiesTree object
    :param results_key: The hexadecimal key used to identify the serialized results in the cache
    :param default_results: The servers default GenomePropertiesResultsWithMatches object
    :return: A GenomePropertiesResultsWithMatches object
    """
    if results_key:
        cached_results = redis_cache.get(results_key)
        if cached_results is not None:
            result1 = load_results_from_serialization(cached_results, properties_tree)
        else:
            result1 = None
        result = result1
    elif default_results is not None:
        result = default_results
    else:
        result = None

    return result
