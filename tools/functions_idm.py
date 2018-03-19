from __future__ import division
import random
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from math import sqrt
from functions_basic import calc_RMSE

from deap import base, creator, tools


"""
/*******************************************************************
Intelligent Driver Model (IDM) functions used to process and analyze CF Data. 

Author: Britton Hammit & Rachel James
E-mail: bhammit1@gmail.com
Date: 01-30-2018
********************************************************************/
"""


### IDM Calibration Functions ###
def run_idm_GA(cf_collections, cxpb, mutpb, m_indpb, ngen, npop, logfile, figfile=None):
    """
    Main function for running the IDM Genetic algorithm.
    :param cf_collections: list of (Instance of Processed Data Class with vehicle trajectory data)
    :param cxpb: The probability of mating two individuals.
    :param mutpb: The probability of mutating an individual.
    :param ngen: Number of generations
    :param npop: Number of individuals in the population
    :param logfile: Log file for recording calibration details about each generation
    :param figfile: Figure file for plotting calibration convergence
    :return: [best_score, best_indiv]
    """

    # Set up GA Structure:
    # http://deap.gel.ulaval.ca/doc/default/overview.html
    creator.create(name="FitnessMin", base=base.Fitness, weights=(-1.0,))
    creator.create(name="Individual", base=list, fitness=creator.FitnessMin)

    toolbox = base.Toolbox()

    # todo Update these ranges based on literature if possible.
    # Ranges are based on integers, so will be divided by 10.
    a_f_min, a_f_max = 1, 40  # same as gipps
    b_f_min, b_f_max = 1, 40  # same as gipps
    delta_min, delta_max = 1, 100  # not divided by 10!!! Is actually an integer
    V_des_min, V_des_max = 1, 400
    t_gap_min, t_gap_max = 1, 50
    g_min_min, g_min_max = 1, 100  # same as gipps

    toolbox.register("attr_a_f", random.randint, a_f_min, a_f_max)
    toolbox.register("attr_b_f", random.randint, b_f_min, b_f_max)
    toolbox.register("attr_delta", random.randint, delta_min, delta_max)
    toolbox.register("attr_V_des", random.randint, V_des_min, V_des_max)
    toolbox.register("attr_t_gap", random.randint, t_gap_min, t_gap_max)
    toolbox.register("attr_g_min", random.randint, g_min_min, g_min_max)

    toolbox.register("individual", tools.initCycle, creator.Individual, (toolbox.attr_a_f, toolbox.attr_b_f,
                                                                         toolbox.attr_delta, toolbox.attr_V_des,
                                                                         toolbox.attr_t_gap, toolbox.attr_g_min), n=1)

    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    # GA
    cx_indpb = 0.5  # percent of the individual that will be switched -- common to use 0.5 https://en.wikipedia.org/wiki/Crossover_(genetic_algorithm)#Uniform_and_half_uniform

    low = [a_f_min, b_f_min, delta_min, V_des_min, t_gap_min, g_min_min]
    up = [a_f_max, b_f_max, delta_max, V_des_max, t_gap_max, g_min_max]

    toolbox.register("mate", tools.cxUniform, indpb=cx_indpb)
    toolbox.register("mutate", tools.mutUniformInt, low=low, up=up, indpb=m_indpb)
    toolbox.register("select", tools.selTournament, tournsize=3)
    toolbox.register("evaluate", evaluate_idm_GA, cf_collections=cf_collections)

    pop = toolbox.population(n=npop)

    log, best_score, best_indiv = evolve_idm_GA(population=pop, toolbox=toolbox, cxpb=cxpb, mutpb=mutpb,
                                                  m_indpb=m_indpb, ngen=ngen,
                                                  logfile=logfile)

    if figfile is not None:
        plt.plot(log['gen'], log['min_score'], label="{} {} {} {}".format(cxpb, mutpb, ngen, npop))
        plt.xlabel("Generation")
        plt.ylabel("Min Fitness of Population")
        plt.legend(loc="upper right")
        plt.savefig(figfile)

    return best_score, best_indiv


def evolve_idm_GA(population, toolbox, cxpb, mutpb, m_indpb, ngen, logfile):
    """
    Evolve a population through the DEAP GA.
    Algorithm altered from eaSimple, provided as part of the DEAP algorithms.py
    :param population: A list of individuals to vary.
    :param toolbox: A :class:`~deap.base.Toolbox` that contains the evolution operators.
    :param cxpb: The probability of mating two individuals.
    :param mutpb: The probability of mutating an individual.
    :param ngen: Number of generations
    :param logfile: Log file for recording calibration details about each generation
    :return: [log, best_score, best_indiv], where the log is a dictionary containing minimum
                scores and best individuals for each generation, the best score, and the best individual
    """
    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", np.mean)
    stats.register("std", np.std)
    stats.register("min", np.min)
    stats.register("max", np.max)

    initiate_idm_calibration_log_file(file=logfile, cxpb=cxpb, mutpb=mutpb, m_indpb=m_indpb,
                                             pop_size=len(population), ngen=ngen)

    # Evaluate the individuals with an invalid fitness
    invalid_ind = [ind for ind in population if not ind.fitness.valid]
    fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
    for ind, fit in zip(invalid_ind, fitnesses):
        ind.fitness.values = fit

    hof_global = tools.HallOfFame(1)
    hof_global.update(population)

    record = stats.compile(population) if stats else {}

    append_to_idm_calibration_log_file(file=logfile, gen=0,
                                              no_unique_indiv=len(invalid_ind), min_score=record['min'],
                                              ave_score=record['avg'], max_score=record['max'],
                                              std_score=record['std'], best_indiv=hof_global[0])

    log = {}
    log['min_score'] = list()
    log['gen'] = list()
    log['hof_local'] = list()
    log['hof_global'] = list()

    # Begin the generational process
    for gen in range(1, ngen+1):
        # Select the next generation individuals
        offspring_a = toolbox.select(population, len(population))

        # Vary the pool of individuals
        offspring = [toolbox.clone(ind) for ind in offspring_a]
        del offspring_a

        # Apply crossover and mutation on the offspring
        # Changed it so that mutation occurs first - then crossover... this way more individuals are impacted

        # Mutation
        for i in range(len(offspring)):
            if random.random() < mutpb:
                offspring[i], = toolbox.mutate(offspring[i])
                del offspring[i].fitness.values

        # Crossover
        for i in range(1, len(offspring), 2):
            if random.random() < cxpb:
                offspring[i - 1], offspring[i] = toolbox.mate(offspring[i - 1], offspring[i])
                del offspring[i - 1].fitness.values, offspring[i].fitness.values

        # Evaluate the individuals with an invalid fitness
        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = fit

        # Update the global HOF to track the best individual seen in the evolution process
        hof_global.update(offspring)
        # Create new HOF to track best individual in this generation.
        hof_local = tools.HallOfFame(1)
        hof_local.update(offspring)

        # Replace the current population by the offspring
        population[:] = offspring
        del offspring

        # Append the current generation statistics to the logbook
        record = stats.compile(population) if stats else {}  # record is a dictionary of the operator and value

        append_to_idm_calibration_log_file(file=logfile, gen=gen,
                                                  no_unique_indiv=len(invalid_ind), min_score=record['min'],
                                                  ave_score=record['avg'], max_score=record['max'],
                                                  std_score=record['std'], best_indiv=hof_local[0])
        log['gen'].append(gen)
        log['min_score'].append(record['min'])
        log['hof_local'].append(hof_local[0])
        log['hof_global'].append(hof_global[0])

        del hof_local

    best_score = toolbox.evaluate(hof_global[0])[0]
    best_indiv = hof_global[0]

    append_to_idm_calibration_log_file(file=logfile, gen=gen,
                                              no_unique_indiv=len(invalid_ind),
                                              min_score=best_score,
                                              ave_score=0, max_score=0,
                                              std_score=0, best_indiv=best_indiv)

    return log, best_score, best_indiv


def evaluate_idm_GA(individual,cf_collections):
    """
    Generate the score for an individual.
        According to literature, it is best to calibrate a model based on the RMSE of spacing;
        therefore, the RMSE_dX was chosen as the fitness function used to evaluate the score
        of each individual.
    :param individual: Array of model parameters: [t_rxn, V_des, a_des, d_des, d_lead, g_min]
    :param cf_collections: list of (Instance of Processed Data Class with vehicle trajectory data)
    :return: Individual Score = RMSE_dX: Float value indicating the individual score
    """
    """
    # Sanity Check Values - From Literature
    a = int(1.0*10)  # comfortable acceleration value, [m/s^2]
    b = int(1.5*10)  # comfortable deceleration value, [m/s^2]
    delta = int(4.0*10)  # acceleration component [unitless] | defines how a decreases as current v approaches desired v
    v_0 = int(33.33*10) # desired velocity [m/s]
    timegap = int(1.0*10) # time gap, [s]
    s_0 = int(2.0*10) # minimum gap (... at standstill?), [m]
    individual = [a,b,delta,v_0,timegap,s_0]
    """

    RMSE_list = list()
    timestep = 0.1  # seconds

    for collection in cf_collections:  # Loop through each car-following collection (event) in the list
        dX_pred_list = list()
        dX_act_list = list()
        vfoll_pred_list = list()
        vfoll_act_list = list()
        vlead_act_list = list()
        afoll_act_list = list()
        afoll_pred_list = list()
        alead_act_list = list()

        # Initialize v_foll, a_foll, and dX values
        vfoll_pred_list.append(collection.v_foll[0])
        dX_pred_list.append(collection.dX[0])
        dX_act_list.append(collection.dX[0])

        for index in xrange(len(collection.dX)-1):
            i = index + 1
            # Pull Actual Variables:
            v_lead = collection.v_lead[i-1]
            v_foll = vfoll_pred_list[i-1]
            dX = dX_pred_list[i-1]

            # Predict Following Vehicle Acceleration
            a_foll_new = idm_predict_a_f(individual=individual,v_foll=v_foll,v_lead=v_lead,dX=dX)

            # Calculate New Velocity & Spacing for the next timestamp
            v_foll_new = v_foll + a_foll_new*timestep
            d_lead = (collection.v_lead[i-1]+collection.v_lead[i])/2*timestep  # distance traveled by lead vehicle
            d_foll = (v_foll+v_foll_new)/2*timestep  # distance traveled by following vehicle
            dX_new = dX - d_foll + d_lead

            # Calculated Variables from Last Iteration
            vfoll_pred_list.append(v_foll_new)

            """
            # Penalize Crashes
            if dX_new < 0:  # severe penalty if crash occurs.
                dX_new = np.inf
            """

            # Initialize with predictions from [0: i-1] and actual variables from [1: i]
            dX_pred_list.append(dX_new)  # This iteration
            dX_act_list.append(collection.dX[i])  # The future "actual" value

            # For sanity checks
            vfoll_act_list.append(collection.v_foll[i])
            afoll_pred_list.append(a_foll_new)
            afoll_act_list.append(collection.a_foll[i])
            vlead_act_list.append(collection.v_lead[i])
            alead_act_list.append(collection.a_lead[i])


        RMSE_dx = calc_RMSE(dX_pred_list, dX_act_list)
        RMSE_list.append(RMSE_dx)

        # Sanity Check
        """
        f, (ax1, ax2, ax3) = plt.subplots(3)
        ax1.plot(dX_act_list, 'r')
        ax1.plot(dX_pred_list, 'b')
        ax1.set_title('Spacing')
        ax2.plot(vfoll_act_list, 'r')
        ax2.plot(vfoll_pred_list, 'b')
        ax2.plot(vlead_act_list, 'g')
        ax2.set_title('Velocity')
        ax3.plot(afoll_act_list, 'r', label='actual')
        ax3.plot(afoll_pred_list, 'b', label='predicted')
        ax3.plot(alead_act_list, 'g', label='lead')
        ax3.set_title('Acceleration')
        ax3.legend()
        f.subplots_adjust(hspace=0.5)
        f.suptitle('IDM Sanity Check, Individual = {}, RMSE = {}'.format(individual, RMSE_dx))
        plt.show()
        """

    # Take a weighted average of the RMSE from each CF event
    index = 0
    length_list = list()
    for collection in cf_collections:
        length_list.append(float(collection.point_count()))
        index += 1
    RMSE_list_weighted = list()
    for i in range(len(cf_collections)):
        factor = length_list[i] / np.sum(length_list)
        RMSE_list_weighted.append(RMSE_list[i] * factor)

    RMSE_all = np.sum(RMSE_list_weighted)

    return RMSE_all,


def idm_predict_a_f(individual,v_foll,v_lead,dX,IDM_choice='original'):
    """
    Predict the following vehicle's velocity
    :param individual: Array of model parameters: [a, b, delta, v_0, timegap, s_0]
    :param v_foll: Float of the following vehicle's velocity [m/s]
    :param v_lead: Float of the lead vehicle's velocity [m/s]
    :param dX: Float of the separation distance between the lead and following vehicle [m]
    :param IDM_choice = 'original' by default, either: 'original', 'improved'
    :return: a_IDM: Predicted following velocity for next time stamp
    """

    a_f, b_f, delta, V_des, t_gap, g_min = individual

    # IDM is a function of follow vehicle space gap, leader velocity, and follower velocity
    # This function has the equations for both IDM and IIDM programmed.  Binary indicate to determine which is desired.

    a = a_f/10.  # comfortable acceleration value, [m/s^2]
    b = b_f/10.  # comfortable deceleration value, [m/s^2]
    delta = delta  # acceleration component [unitless] | defines how a decreases as current v approaches desired v
    v_0 = V_des/10.  # desired velocity [m/s]
    timegap = t_gap/10.  # time gap, [s]
    s_0 = g_min/10.  # minimum gap (... at standstill?), [m]

    """
    # Parameter Values from the literature
    a = 1.0 # comfortable acceleration value, [m/s^2]
    b = 1.5 # comfortable deceleration value, [m/s^2]
    delta = 4.0 # acceleration component [unitless] | defines how a decreases as current v approaches desired v
    v_0 = 33.33 # desired velocity [m/s]
    timegap = 1.0 # time gap, [s]
    s_0 = 2.0 # minimum gap (... at standstill?), [m]
    """

    # Values from Data
    v_f = v_foll  # follower velocity at time t, [m/s]
    v_l = v_lead  # leader velocity at time t, [m/s]
    dV = v_f - v_l  # follower - leader, defined in Kesting, Trieber, and Helbing, 2010
    s = dX  # current space gap between leader and follower at time t, [m]

    # Calculations
    s_star = s_0 + max(0.0, v_f*timegap+(v_f *dV)/(2 * sqrt(a * b)))  # desired safe gap [m]

    """
    # Precise Defintions 
    equilibrium_term = v_f * timegap # part one of s_star
    dynamical_term = (v_f * v_differential) / (2 * sqrt(a*b))
    intelligent_braking = equilibrium_term + dynamical_term
    s_star = s_0 + max(0.0, intelligent_braking) # desired safe gap [m]
    a_free = a * (1 - pow(v_f/v_0, delta)) # free road acceleration strategy
    a_brake = (- a) * pow(s_star/s, 2) # deceleration strategy
    a_IDM = v_free + v_brake
    """

    if IDM_choice == 'original':
        a_IDM = a * (1 - pow(v_f / v_0, delta) - pow(s_star / s, 2))

    elif IDM_choice == 'improved':
        z = s_star / s

        if v_f <= v_0:
            a_free = a * (1 - pow(v_f / v_0, delta))
            if z >= 1:
                a_IDM = a * (1 - pow(z, 2))
            else:
                a_IDM = a_free * (1 - (pow(z, (2 * a) / a_free)))
        else:
            a_free = - b * (1 - pow(v_0 / v_f, (a * delta) / b))
            if z >= 1:
                a_IDM = a_free + a * (1 - pow(z, 2))
            else:
                a_IDM = a_free

    return a_IDM


### Log Files ###
def initiate_idm_calibration_log_file(file, cxpb, mutpb, m_indpb, pop_size, ngen):
    file.write('IDM CFM Calibration - DEAP GA Implementation')
    file.write('\n')
    file.write('cxpb,mutpb,m_indpb,pop_size,ngen')
    file.write('\n')
    file.write('{},{},{},{},{}'.format(cxpb, mutpb, m_indpb, pop_size, ngen))
    file.write('\n')
    file.write('Gen,No Unique Indiv,Min Score,Ave Score,Max Score,Std Score,')
    file.write('a_f,b_f,delta,V_des,t_gap,g_min')
    file.write('\n')

    print 'IDM CFM Calibration - DEAP GA Implementation'
    print 'cxpb: {} | mutpb: {} | m_indpb: {} | pop_size: {} | ngen: {}'.format(cxpb, mutpb, m_indpb, pop_size, ngen)
    print '%4s | %4s | %8s | %8s | %8s | %8s | %4s, %4s, %4s, %4s, %4s, %4s' % (
    'gen', 'cnt', 'min', 'ave', 'max', 'std', 'a_f', 'b_f', 'del', 'V', 't', 'g')


def append_to_idm_calibration_log_file(file, gen, no_unique_indiv, min_score, ave_score, max_score, std_score,
                                              best_indiv):
    file.write('{},{},{},{},{},{},'.format(gen, no_unique_indiv, min_score, ave_score, max_score, std_score))
    file.write(
        '{},{},{},{},{},{}'.format(best_indiv[0]/10., best_indiv[1]/10.,best_indiv[2], best_indiv[3]/10., best_indiv[4]/10., best_indiv[5]/10.))
    file.write('\n')

    print '%4.0f | %4.0f | %8.3f | %8.3f | %8.3f | %8.3f | %4.1f, %4.1f, %4.0f, %4.1f, %4.1f, %4.1f' % (
    gen, no_unique_indiv, min_score, ave_score, max_score, std_score, best_indiv[0]/10., best_indiv[1]/10.,
    best_indiv[2], best_indiv[3]/10., best_indiv[4]/10., best_indiv[5]/10.)


def initiate_idm_calibration_summary_file(file):
    file.write('iteration,time,cxpd,mutpd,m_indpb,ngen,npop,score,a_f,b_f,delta,V_des,t_gap,g_min')
    file.write('\n')


def append_to_idm_calibration_summary_file(file, elapsed_time, iteration, cxpb, mutpb, m_indpb, ngen, npop,
                                                  score, best_indiv):
    file.write('{},'.format(iteration))
    file.write('{},'.format(elapsed_time))
    file.write('{},{},{},{},{},'.format(cxpb, mutpb, m_indpb, ngen, npop))
    file.write('{},'.format(score))
    file.write(
        '{},{},{},{},{},{}'.format(best_indiv[0]/10., best_indiv[1]/10., best_indiv[2], best_indiv[3]/10.,
                                   best_indiv[4]/10., best_indiv[5]/10.))
    file.write('\n')


def initiate_idm_calibration_cs_summary_file(file):
    file.write('trip_set_no,trip_no,driver_id,adverse_cond,trip_cond,time,score,a_f,b_f,delta,V_des,t_gap,g_min')
    file.write('\n')


def append_to_idm_calibration_cs_summary_file(file, elapsed_time, trip_set_no, trip_no, driver_id,
                                                            adverse_cond, trip_cond, score, best_indiv):
    file.write('{},'.format(trip_set_no))
    file.write('{},'.format(trip_no))
    file.write('{},{},{},'.format(driver_id, adverse_cond, trip_cond))
    file.write('{},'.format(elapsed_time))
    file.write('{},'.format(score))
    file.write(
        '{},{},{},{},{},{}'.format(best_indiv[0]/10., best_indiv[1]/10., best_indiv[2], best_indiv[3]/10.,
                                   best_indiv[4]/10., best_indiv[5]/10.))
    file.write('\n')

def initiate_201802Calib_idm_summary_file(file):
    file.write('2018-02-15 IDM Calibration Summary File')
    file.write('\n')
    # Trip Info
    file.write('trip_no,total_run_time_sec,')
    file.write('driver_id,total_trip_length_min,total_trip_length_km,')
    file.write('stac_availability,')
    file.write('time_bin,day,month,year,')
    # Car-following
    file.write('time_cf_percent,time_cf_min,no_cf_events,')
    # Demographics
    file.write('gender,age_group,ethnicity,race,education,marital_status,living_status,work_status,')
    file.write('household_population,income,')
    file.write('miles_driven_last_year,')
    # Behavior
    file.write('frequency_tailgating,frequency_disregarding_speed_limit,frequency_aggressive_braking,')
    # Calibration Info
    file.write('calibration_time_sec,calibration_score,a_f,b_f,delta,V_des,t_gap,g_min')
    file.write('\n')


def append_to_201802Calib_idm_summary_file(file, trip_no, driver_id, point_collection, cf_collections,
                                                  stac_data_available, demographics_data, behavior_data, calib_time,
                                                  calib_score, calib_best_indiv, total_time):
    # Trip Info
    file.write('{},{},'.format(trip_no,total_time))
    file.write('{},{},{},'.format(driver_id, point_collection.time_elapsed() / 60,
                                     point_collection.dist_traveled()))
    file.write("{},".format(stac_data_available))
    time1, day, month, year = point_collection.time_day_month_year()
    file.write("{},{},{},{},".format(time1, day, month, year))

    # Car-following
    file.write("{},{},{},".format(point_collection.percent_car_following(), point_collection.time_car_following(),
                                        len(cf_collections)))

    # Driver Demographics
    if demographics_data == None:
        for j in range(11):
            file.write('{},'.format(np.nan))
    else:
        # file.write('Gender,Age Group,Ethnicity,Race,Education,Marital Status,Living Status,Work Status,')
        file.write('{},{},{},'.format(demographics_data[1], demographics_data[2], demographics_data[3]))
        file.write('{},{},{},'.format(demographics_data[4], demographics_data[6], demographics_data[7]))
        file.write('{},{},'.format(demographics_data[8], demographics_data[10]))
        # file.write('Income,Household Population,')
        file.write('{},{},'.format(demographics_data[11], demographics_data[12]))
        # file.write('Miles Driven Last Year,')
        file.write('{},'.format(demographics_data[44]))

    # Driver Behavior
    if behavior_data == None:
        file.write("{},{},{},".format(np.nan, np.nan, np.nan))
    else:
        # file.write('Frequency of Tailgating,Frequency of Disregarding Speed Limit,Frequency of Aggressive Braking')
        file.write('{},{},{},'.format(behavior_data[3], behavior_data[12], behavior_data[24]))

    # Calibration
    file.write('{},'.format(calib_time))
    file.write('{},'.format(calib_score))
    file.write(
        '{},{},{},{},{},{}'.format(calib_best_indiv[0]/10., calib_best_indiv[1]/10., calib_best_indiv[2], calib_best_indiv[3]/10.,
                                   calib_best_indiv[4]/10., calib_best_indiv[5]/10.))


    file.write("\n")


# todo later.
### Plotting/Analysis Functions ###
def idm_sensitivity_analysis_plot(summary_file, date, save_path, CXPB, MUTPB, NGEN, NPOP):
    df = pd.read_csv(filepath_or_buffer=summary_file, delimiter=',', header=0)

    # Score Plot
    fig, axes = plt.subplots(nrows=len(CXPB), ncols=len(MUTPB), figsize=(15, 12))  # figsize=(13,11)
    fig.suptitle('Gipps Calibration Sensitivity Analysis | {} Generations | {}'.format(NGEN, date), fontsize=16,
                 fontweight='bold')
    for i in range(len(CXPB)):
        for j in range(len(MUTPB)):
            # Create data frame for specific plot
            df_temp = df[(df.cxpd == CXPB[i]) & (df.mutpd == MUTPB[j])]
            no_iterations = len(df_temp[df_temp.npop == NPOP[0]])
            df_temp.plot(x='npop', y='score', kind='scatter', subplots=True, ax=axes[i, j],
                         label='{} Iterations'.format(no_iterations), color='b')
            axes[i, j].set_title('cxpb: {} | mutpb: {}'.format(CXPB[i], MUTPB[j]), fontweight='bold')

            # Y Limits
            axes[i, j].set_ylim([0.1, 0.35])  # Vehicle 13 & 41
            # axes[i,j].set_ylim([0.45,0.7])  # Vehicle 35
            axes[i, j].set_ylabel('Score: RMSE of dX [m]', fontsize=12)

            # X Limits
            min_pop = min(NPOP)
            max_pop = max(NPOP)
            diff_pop = max_pop - min_pop
            buffer_dist = diff_pop * 0.2 / 0.6  # 20% buffer on each side
            axes[i, j].set_xlim([min_pop - buffer_dist, max_pop + buffer_dist])
            axes[i, j].set_xlabel('Population Size', fontsize=12)
            del buffer_dist

            # Averages & Standard Deviations Per Population
            ave_list = list()  # list of average scores
            std_list = list()  # list of std of scores
            for npop in NPOP:
                df_temp2 = df_temp[df_temp.npop == npop]
                ave_list.append(np.nanmean(df_temp2.score))
                std_list.append(np.nanstd(df_temp2.score))
            # Horizontal line for each Average
            x_buffer_dist = diff_pop * 0.15 / 0.7  # 10% buffer on each side
            y_buffer_dist = (0.35 - 0.1) * 0.02 / 0.96  # 2% buffer above
            bbox = dict(boxstyle="round,pad=0.1", fc='white', ec='white', lw=0, alpha=0.8)
            for k in range(len(NPOP)):
                axes[i, j].plot((NPOP[k] - x_buffer_dist, NPOP[k] + x_buffer_dist), (ave_list[k], ave_list[k]),
                                color='r', linestyle='--', label='ave')
                axes[i, j].annotate(('Ave: {:4.3f}'.format(ave_list[k])),
                                    xy=(NPOP[k] - x_buffer_dist, ave_list[k] + y_buffer_dist),
                                    xytext=(NPOP[k] - x_buffer_dist, ave_list[k] + y_buffer_dist), color='g', bbox=bbox,
                                    fontweight='bold')
                axes[i, j].annotate(('Std: {:4.3f}'.format(std_list[k])),
                                    xy=(NPOP[k] - x_buffer_dist, ave_list[k] - y_buffer_dist * 2.5),
                                    xytext=(NPOP[k] - x_buffer_dist, ave_list[k] - y_buffer_dist * 2.5), color='g',
                                    bbox=bbox, fontweight='bold')

            del min_pop, max_pop, diff_pop, npop, ave_list, std_list, k, x_buffer_dist, y_buffer_dist, bbox

            del df_temp

    plt.tight_layout()
    plt.subplots_adjust(hspace=0.6, wspace=0.6)
    plt.subplots_adjust(top=0.92, bottom=0.08)
    # plt.show()

    fig.savefig(os.path.join(save_path, '{}'.format(date)))


def idm_convergence_plot(log_file, date, save_path):
    df = pd.read_csv(filepath_or_buffer=log_file, delimiter=',', header=3)
    convergence_variables = ['Min Score', 'Best: T_rxn', 'Best: V_des', 'Best: a_des', 'Best: d_des', 'Best: d_lead',
                             'Best: g_min']
    # Score Plot
    fig, axes = plt.subplots(nrows=len(convergence_variables), ncols=1, figsize=(12, 16))  # figsize=(13,11)
    fig.suptitle('Gipps Calibration Convergence | {}'.format(date), fontsize=16, fontweight='bold')

    plot_pos_index = 0
    for var in convergence_variables:
        # Create data frame for specific plot
        if var == 'Min Score':
            color = 'darkgreen'
        elif var == 'Best: d_des':
            color = 'maroon'
        else:
            color = 'navy'
        df.plot(x='Gen', y=var, kind='line', subplots=True, ax=axes[plot_pos_index], color=color,
                label='value by generation')
        axes[plot_pos_index].set_title('{}'.format(var))
        axes[plot_pos_index].legend(loc='lower right')

        # Identify Generation with Last Score Change
        last_change = 0
        for j in range(len(df['Gen']) - 1):
            if df[var][j] != df[var][j + 1]:
                last_change = df['Gen'][j + 1]

        axes[plot_pos_index].axvline(last_change, color='r', linestyle='--', label='last change')

        # X Limits
        axes[plot_pos_index].set_xlabel('')

        plot_pos_index += 1

    plt.tight_layout()
    plt.subplots_adjust(hspace=.8, wspace=0.2)
    plt.subplots_adjust(top=0.92, bottom=0.03)
    # plt.show()

    fig.savefig(os.path.join(save_path, '{}'.format(date)))


def idm_sensitivity_analysis_file(summary_file, date, save_path, CXPB, MUTPB, M_INDPB, NGEN, NPOP):
    df_summary = pd.read_csv(filepath_or_buffer=summary_file, delimiter=',', header=0)

    # Set up Calibration Summary File
    target = open(os.path.join(save_path, '{}_calibration_summary.csv'.format(date)), 'w')
    target.write('GroupNo,cxpb,mutpb,m_indpb,')
    target.write('ngen,npop,')
    target.write('score_ave,score_std,score_min,')
    target.write('time_ave,time_std,time_min,')
    target.write('last_gen_ave,last_gen_std,last_gen_min,freq_converged')
    target.write('\n')

    group_no = 0  # Counter for each set of GA parameters
    iteration_no = 0  # Counter for each individual iteration
    for i in range(len(CXPB)):
        for j in range(len(MUTPB)):
            for k in range(len(NPOP)):
                for m in range(len(M_INDPB)):
                    for n in range(len(NGEN)):
                        group_no += 1
                        # Create data frame for specific plot
                        df_summary_temp = df_summary[(df_summary.cxpd == CXPB[i]) & (df_summary.mutpd == MUTPB[j]) & (
                        df_summary.npop == NPOP[k]) & (df_summary.m_indpb == M_INDPB[m])]
                        no_iterations = len(df_summary_temp)

                        # Averages & Standard Deviations Per Population -- Scores
                        ave_scores = np.nanmean(df_summary_temp.score)
                        std_scores = np.nanstd(df_summary_temp.score)
                        min_scores = df_summary_temp.score.min()

                        # Averages & Standard Deviations Per Population -- CompTime
                        ave_time = np.nanmean(df_summary_temp.time)
                        std_time = np.nanstd(df_summary_temp.time)
                        min_time = df_summary_temp.time.min()

                        # Looking at Convergence/Generation with the lowest reported MIN score.
                        last_change = list()
                        converge_counter = 0
                        for iteration_no in df_summary_temp.iteration:
                            log_filename = '{}_{}_logfile.csv'.format(date, iteration_no)
                            log_file = open(os.path.join(save_path, log_filename), 'r')
                            df_log = pd.read_csv(filepath_or_buffer=log_file, delimiter=',', header=3)

                            # Identify Generation with Last Score Change
                            for p in range(len(df_log['Gen']) - 1):
                                if df_log['Min Score'][p] != df_log['Min Score'][p + 1]:
                                    last_change_temp = df_log['Gen'][p + 1]
                            last_change.append(last_change_temp)
                            if last_change_temp < NGEN[n]:
                                converge_counter += 1

                        ave_last_change = np.nanmean(last_change)
                        std_last_change = np.nanstd(last_change)
                        min_last_change = np.nanmin(last_change)

                        # Summary Calibration File
                        target.write('{},{},{},{},'.format(group_no, CXPB[i], MUTPB[j], M_INDPB[m]))
                        target.write('{},{},'.format(NGEN[n], NPOP[k]))
                        target.write('{},{},{},'.format(ave_scores, std_scores, min_scores))
                        target.write('{},{},{},'.format(ave_time, std_time, min_time))
                        target.write(
                            '{},{},{},{}'.format(ave_last_change, std_last_change, min_last_change, converge_counter))
                        target.write('\n')
    target.close()
