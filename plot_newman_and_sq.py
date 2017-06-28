# coding: utf-8
from __future__ import print_function
import sys, os, glob
import tqdm
import time, copy

import numpy as np
from numpy.linalg import norm

from scipy.misc import comb
from math import floor, ceil, log
import matplotlib.pyplot as plt
import artm

from itertools import groupby

from collections import defaultdict

import codecs

from document_helper import pn_folder, vw_folder, files_total, domain_path, data_results_save
from segmentation import segmentation_evaluation

from coherences import coh_newman, coh_mimno #, #coh_cosine
from intra_coherence import coh_semantic, coh_toplen
    
    

def create_model(dictionary, num_tokens, num_document_passes):

    tn = ['topic {}'.format(i) for i in range(1, 20)]
    scores = [artm.PerplexityScore(name='PerplexityScore', dictionary=dictionary),
    artm.TopTokensScore(name='TopTokensScore', num_tokens=10), # web version of Palmetto works only with <= 10 tokens
    artm.SparsityPhiScore(name='SparsityPhiScore'),
    artm.SparsityThetaScore(name='SparsityThetaScore')]
                      
    model = artm.ARTM(topic_names=tn, regularizers=[], cache_theta=True, scores=scores)

    model.initialize(dictionary=dictionary)
    model.num_document_passes = num_document_passes
    
    return model


coh_names = ['newman', 'mimno']
coh_names_top_tokens = ['newman', 'mimno']
coh_funcs = [coh_newman, coh_mimno]


#coh_names = ['newman', 'mimno', 'cosine', 'semantic', 'toplen']
#coh_names_top_tokens = ['newman', 'mimno', 'cosine']
#coh_funcs = [coh_newman, coh_mimno, coh_cosine, coh_semantic, coh_toplen]
#coh_funcs = [coh_newman, coh_mimno]


window = 10
threshold = 0.02
cosine_num_top_tokens = 10
focon_threshold = 5

num_passes_list = range(1, 15)
#num_passes_list = [1, 2, 3, 4, 5, 6, 7]
num_passes_list = [1, ]
num_passes_last = 0

num_top_tokens = 10
num_working_files = 20




# Vowpal Wabbit
batch_vectorizer = None


if len(glob.glob(os.path.join(pn_folder, vw_folder, '*.batch'))) < 1:
    batch_vectorizer = artm.BatchVectorizer(data_path=os.path.join(pn_folder, vw_folder, 'vw.txt'),
                                            data_format='vowpal_wabbit',
                                            target_folder=os.path.join(pn_folder, vw_folder)) 
else:
    batch_vectorizer = artm.BatchVectorizer(data_path=os.path.join(pn_folder, vw_folder),
                                            data_format='batches')


dictionary = artm.Dictionary()

dict_path = os.path.join(pn_folder, vw_folder, 'dict.dict')

if not os.path.isfile(dict_path):
    dictionary.gather(data_path=batch_vectorizer.data_path)
    dictionary.save(dictionary_path=dict_path)

dictionary.load(dictionary_path=dict_path)


dictionary.filter(min_df=2, max_df_rate=0.4)

N = 1
# model
model = create_model(dictionary=dictionary,
                     num_tokens=num_top_tokens,
                     num_document_passes=N) 

# number of cycles
num_of_restarts = 1

num_averaging_iterations = 1


segm_quality_carcass = {
    'soft': np.array([]),
    'harsh': np.array([])
}

def create_coherences_framework(coh_names):
    coherences_carcass = defaultdict(dict)
    for cn in coh_names:
        for mode in ['mean-of-means', 'mean-of-medians', 'median-of-means', 'median-of-medians']:
            coherences_carcass[cn][mode] = np.array([])
    return coherences_carcass

    
def measures_append(arr, index, coh_name, where, what):
    arr[index][coh_name][where] = (np.append(arr[index][coh_name][where], what))
    
def append_all_measures(coherences_tmp, window, threshold, coh_name, coh_list):
    index = (window, threshold)
    
    measures_append(coherences_tmp, index, coh_name, 'mean-of-means', np.mean(coh_list['means']))
    measures_append(coherences_tmp, index, coh_name, 'mean-of-medians', np.mean(coh_list['medians']))
    measures_append(coherences_tmp, index, coh_name, 'median-of-means', np.median(coh_list['means']))
    measures_append(coherences_tmp, index, coh_name, 'median-of-medians', np.median(coh_list['medians']))





t0 = time.time()

indent = '    '
indent_number = 0

for restart_num in range(num_of_restarts):
    np.random.seed(restart_num * restart_num + 42)
    
    topic_model_data, phi_numpy_matrix = model.master.attach_model('pwt')
    
    random_init = np.random.random_sample(phi_numpy_matrix.shape)
    random_init /= np.sum(random_init, axis=0)
    np.copyto(phi_numpy_matrix, random_init)
    
    # list of segmentation evaluations - to be further used for plotting
    segm_quality = copy.deepcopy(segm_quality_carcass)

    # list of coherences
    coherences = {(window, threshold): create_coherences_framework(coh_names)}
    #coherences = {(window, threshold): copy.deepcopy(coherences_carcass)}

    # range of models with different segmentation qualities
    for num_passes_total in num_passes_list:
        print('************************\n({0:>2d}:{1:>2d}) num_passes: {2}'.format(
            int(time.time()-t0)//60//60,
            int(time.time()-t0)//60%60,
            num_passes_total)
        )

        # teach model
        print('({0:>2d}:{1:>2d}) teaching model'.format(
            int(time.time()-t0)//60//60,
            int(time.time()-t0)//60%60)
        )
        indent_number += 1

        model.fit_offline(
            batch_vectorizer=batch_vectorizer,
            num_collection_passes=num_passes_total-num_passes_last
        )
        num_passes_last = num_passes_total
        indexes = None

        # read model parameters
        phi = model.get_phi()
        theta = model.get_theta()
        phi_cols = list(phi.columns)
        phi_rows = list(phi.index)
        theta_cols = list(theta.columns)
        theta_rows = list(theta.index)
        phi_val = phi.values
        theta_val = theta.values

        # initialize tmp lists
        segm_quality_tmp = copy.deepcopy(segm_quality_carcass)
        #coherences_tmp = {(window, threshold): copy.deepcopy(coherences_carcass)}
        coherences_tmp = {(window, threshold): create_coherences_framework(coh_names)}

        # start iterations (to fill tmp-lists)
        for iteration in range(num_averaging_iterations):
            print('({0:>2d}:{1:>2d}){2}iteration: {3}'.format(
                int(time.time()-t0)//60//60,
                int(time.time()-t0)//60%60,
                indent*indent_number,
                iteration)
            )

            indent_number += 1

            # get range of files to work with
            files = files_total[:100]

            # different types of coherence
            for i in range(len(coh_names)):
                coh_name = coh_names[i]
                coh_func = coh_funcs[i]

                print('({0:>2d}:{1:>2d}){2}{3}'.format(
                    int(time.time()-t0)//60//60,
                    int(time.time()-t0)//60%60,
                    indent*indent_number, coh_name)
                )

                if (coh_name in coh_names_top_tokens):
                    coh_list = coh_func(
                        window=window, num_top_tokens=num_top_tokens,
                        model=model, topics=model.topic_names,
                        files=files, files_path=domain_path
                    )

                append_all_measures(coherences_tmp, window, threshold, coh_name, coh_list)
                    
            indent_number -= 1
            indent_number -= 1

            
            # current segmentation quality
            print('({0:>2d}:{1:>2d}){2}segmentation evaluation'.format(
                int(time.time()-t0)//60//60,
                int(time.time()-t0)//60%60,
                indent*indent_number)
            )
            
            cur_segm_eval, indexes = (
                segmentation_evaluation(
                    topics=model.topic_names,
                    collection=files_total, collection_path=domain_path,
                    files=files,
                    phi_val=phi_val, phi_cols=phi_cols, phi_rows=phi_rows,
                    theta_val=theta_val, theta_cols=theta_cols, theta_rows=theta_rows,
                    indexes=indexes
                )
            )
            segm_quality_tmp['soft'] = np.append(
                segm_quality_tmp['soft'], cur_segm_eval['soft']
            )
            segm_quality_tmp['harsh'] = np.append(
                segm_quality_tmp['harsh'], cur_segm_eval['harsh']
            )

            # printing parametres
            print('({0:>2d}:{1:>2d}){2}window: {3}, threshold: {4}'.format(
                int(time.time()-t0)//60//60,
                int(time.time()-t0)//60%60,
                indent*indent_number,
                window, threshold)
            )

            indent_number += 1

            
        # making appends to the result lists
        # segmentation
        for s in segm_quality:
            segm_quality[s] = (
                np.append(segm_quality[s],
                          np.mean(segm_quality_tmp[s]))
            )
        # coherences
        for name in coherences[(window, threshold)]:
            for s in coherences[(window, threshold)][name]:
                coherences[(window, threshold)][name][s] = (
                    np.append(coherences[(window, threshold)][name][s],
                              np.mean(coherences_tmp[(window, threshold)][name][s]))
                )

        indent_number -= 1

    data_results_save(pars_name=['window', 'threshold'],
        pars_segm=segm_quality,
        pars_coh=coherences,
        coh_names=coh_names,
        file_name=str(restart_num))
    toptokens_data = model.score_tracker['TopTokensScore']
    max_iter = num_passes_list[-1]
    with codecs.open("toptokens2.txt", "w", encoding="utf8") as f:
        for iter in range(max_iter):
            f.write(u'============\n')
            f.write(u'{}\n'.format(iter))
            for topic_name in model.topic_names:
                f.write(u'{}\n'.format(topic_name))
                #print(toptokens_data.tokens)
                #print(toptokens_data.tokens[iter-1].keys())
                #print( (topic_name) )
                for (token, weight) in zip(toptokens_data.tokens[iter][topic_name],
                                           toptokens_data.weights[iter][topic_name]):
                    f.write(u"{} {}\n".format(token, weight))
                f.write('\n')
                # TODO 
                # f.write("local coherence: {}".format()
            # TODO 
            f.write(u"segm qual strict: {}\n".format(segm_quality['harsh'][iter]))
            f.write(u"segm qual soft: {}\n".format(segm_quality['soft'][iter]))

            f.write(u"coh newman: {}\n".format(coherences[(window, threshold)]['newman']['mean-of-means'][iter]))
            f.write(u"coh mimno: {}\n".format(coherences[(window, threshold)]['mimno']['mean-of-means'][iter]))
            
                
