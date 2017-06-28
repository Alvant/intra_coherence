# coding: utf-8
from __future__ import print_function, division
from munkres import Munkres # for Hungarian algorithm


import codecs, re
import sys, os, glob
import tqdm
import time, copy

import numpy as np
from numpy.linalg import norm
from scipy import stats 
from scipy.misc import comb
from math import floor, ceil, log
import matplotlib.pyplot as plt
from itertools import groupby

from document_helper import get_orig_labels, get_docnum, calc_doc_ptdw, read_file_data


            
def calc_cost_matrix(topics, role_nums, files, files_path,
                       phi_val, phi_cols, phi_rows,
                       theta_val, theta_cols, theta_rows):
    t_start = time.time()
    labeling_time = 0        
    word = ''
    data = ''
    original_topic_num = 0
    
    known_words = phi_rows

    sum_p_tdw = np.zeros((len(role_nums), len(topics)))
    hits_num = np.zeros((len(role_nums), len(topics)))
    
    for f in tqdm.tqdm(files):
        if "txt" not in f:
            continue
        doc_num = get_docnum(f)
        if doc_num not in theta_cols:
            continue
        data = read_file_data(f)

        data_filtered, doc_ptdw = calc_doc_ptdw(
            f=f, topics=topics, known_words=known_words,
            phi_val=phi_val, phi_rows=phi_rows,
            theta_val=theta_val, theta_cols=theta_cols
        )
        original_topic_labels = get_orig_labels(data_filtered, data)
        for i, original_topic_num in enumerate(original_topic_labels):
            sum_p_tdw[:, original_topic_num] += doc_ptdw[i]
        argmax_indices = np.argmax(doc_ptdw, axis=1)
        np.add.at(hits_num, [argmax_indices, original_topic_labels], 1)
    return {'soft': sum_p_tdw, 'harsh': hits_num}

def calc_solution_cost(indexes, cost_matrix):
    
    res_s = 0
    for row, column in indexes['soft']:
        value = cost_matrix['soft'][row][column]
        res_s += value
    res_h = 0
    for row, column in indexes['harsh']:
        value = cost_matrix['harsh'][row][column]
        res_h += value

    return {'soft': res_s, 'harsh': res_h}

def segmentation_evaluation(topics, collection, collection_path, files,
                            phi_val, phi_cols, phi_rows,
                            theta_val, theta_cols, theta_rows,
                            indexes=None):
    t_start = time.time()

    mnkr = Munkres()
    res = {'soft': 0, 'harsh': 0}
    res_list = []
    
    #return res, {'soft': [], 'harsh': []}
    topics_number = len(topics)
    '''
    if (indexes is not None):
        # segmentation evaluation
        top_role_play_working_files = (
            topic_role_playing(
                topics=topics, role_nums=range(1, len(topics)+1),
                files=files, files_path=collection_path,
                phi_val=phi_val, phi_cols=phi_cols, phi_rows=phi_rows,
                theta_val=theta_val, theta_cols=theta_cols, theta_rows=theta_rows,
                indexes=indexes)
        )
    else:'''
    # role playing
    top_role_play = (
        calc_cost_matrix(
            topics=topics, role_nums=range(1, len(topics)+1),
            files=files, files_path=collection_path,
            phi_val=phi_val, phi_cols=phi_cols, phi_rows=phi_rows,
            theta_val=theta_val, theta_cols=theta_cols, theta_rows=theta_rows)
    )

    indexes = {'soft': [], 'harsh': []}

    for s in ['soft', 'harsh']:
        matrix = top_role_play[s]
        #cost_matrix2 = mnkr.make_cost_matrix(matrix,
        #                               lambda cost: sys.maxsize - cost)
        cost_matrix = []
        for row in matrix:
            cost_row = [(sys.maxsize - col) for col in row]
            cost_matrix += [cost_row]
        indexes[s] = mnkr.compute(cost_matrix)
        #print(indexes[s])
        #print(mnkr.compute(cost_matrix2))
    
    # segmentation evaluation
    res = calc_solution_cost(indexes=indexes, cost_matrix=top_role_play)

    t_end = time.time()
    print("segmentation_evaluation: {} seconds".format(t_end - t_start))

    return res, indexes