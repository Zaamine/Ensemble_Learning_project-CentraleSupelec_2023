# import necessary libraries
import pandas as pd
import numpy as np
import os
import glob
import spacy
import nltk
import re
import json as json
import time as time


# modeling
import xgboost as xg
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import AdaBoostRegressor
from sklearn.ensemble import BaggingRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from lightgbm import LGBMRegressor
from sklearn.ensemble import VotingRegressor
from sklearn.ensemble import StackingRegressor
import lightgbm as lgb
from sklearn.linear_model import LinearRegression
from catboost import CatBoostRegressor


# Dimension reduction and clustering
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.manifold import TSNE


# model selection and hyper-parameters tuning
from sklearn.preprocessing import StandardScaler,MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.model_selection import RandomizedSearchCV
from sklearn.model_selection import cross_validate
from hyperopt import STATUS_OK, Trials, fmin, hp, tpe   #Bayesian Search

# for scoring
from sklearn.metrics import mean_absolute_error,mean_squared_error,r2_score,mean_absolute_percentage_error

# for visualizations
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import norm
from scipy.stats import probplot
from PIL import Image
from graphviz import Digraph



# Load spaCy model  for string encoding
nlp = spacy.load("en_core_web_sm")

# Download the stop words
stop_words = set(nltk.corpus.stopwords.words('english'))


__all__ = ["sns", 
           "np", 
           "pd", 
           "plt",
           "xg",
           "norm",
           "probplot",
           "Image",
           "Digraph",
           "time",
           "mean_absolute_error",
           "mean_squared_error",
           "r2_score",
           "mean_absolute_percentage_error",
           "nlp",
           "stop_words",
           "StandardScaler",
           "MinMaxScaler",
           "train_test_split",
           "RandomizedSearchCV",
           "cross_validate",
           "STATUS_OK",
           "Trials",
           "fmin",
           "hp",
           "tpe",
           "DecisionTreeRegressor",
           "AdaBoostRegressor",
           "BaggingRegressor",
           "RandomForestRegressor",
           "ExtraTreesRegressor",
           "GradientBoostingRegressor",
           "HistGradientBoostingRegressor",
           "LGBMRegressor",
           "VotingRegressor",
           "StackingRegressor",
           "LinearRegression",
           "CatBoostRegressor",
           "PCA",
           "KMeans",
           "TSNE",
           "get_cartesian",
           "lambda_n",
           "target_encoding",
           "clean_text",
           "process_batch",
           "encode_texts",
           "compare_norm_dist",
           "preprocess",
           "scores",
           "load_params",
           "file_paths",
           "file_paths_global",
           "json",
           "lgb",
           "stacking_prediction",
           "vote_prediction"
          ]

file_paths = {'data':'../dataset/AB_NYC_2019.csv',
              'name_tsne': '../dataset/name_tsne.csv',
              'text_tsne': '../dataset/text_tsne.csv',
              'opendata' : '../dataset/airbnb-listings.csv'}

file_paths_global = {'data':'dataset/AB_NYC_2019.csv',
              'name_tsne': 'dataset/name_tsne.csv',
              'text_tsne': 'dataset/text_tsne.csv',
              'opendata' : 'dataset/airbnb-listings.csv'}

############# HELPER FUNCTIONS WE DEVELOPPED #############################
# - get_cartesian: Converts latitude and longitude arrays into (x,y,z) coordinates
# - lambda_n : Compute the blending factor using a sigmoid function.
# - target_encoding: Target encoding using blending factor and accounting for hierarchy.
# - clean_text: A function to remove stop words and special characters
# - process_batch : Function to encode a single batch of texts
# - encode_texts : Function to encode many texts by batches
# - compare_norm_dist : Compares a series normal distribution and return threshold to remove outliers.
# - preprocess :  Preprocesses raw file to return a feature matrix X (dataframe) and target values y (dataframe)
# - scores : Compute MAE, MSE, RMSE, R2 and MAPE scores and plot prediction errors
# - load_params : load json files containing tuned models' parameters
# - vote_prediction : Homemade voting algorithm that computes predictions and make a weighted sum or average
# - stacking_prediction : Homemade stacking algorithm that computes predictions on k-fold to feed a final metamodel (linear regression)
##########################################################################


def get_cartesian(lat=None,lon=None):
    '''
    Converts latitude and longitude arrays into (x,y,z) coordinates
    Input :
          latitude as array
          longitude as array
    Output :
          x,y,z cartesian coordinates
    '''
    # Change degrees to radians
    lat, lon = np.deg2rad(lat), np.deg2rad(lon)
    R = 1 # radius of the earth = 6371 km but not needed as we will normalize

    # Convert to cartesian
    x = R * np.cos(lat) * np.cos(lon)
    y = R * np.cos(lat) * np.sin(lon)
    z = R *np.sin(lat)

    return x,y,z

def lambda_n(n,k,f):
    '''
    Compute the blending factor using a sigmoid function.
    
    Inputs :
        n : Pandas series with the counts for each category (the id must be the categories)
        k : translation parameter. The sigmoid give 0.5 when n=k
        f:  steepness parameter. The lower it is, the steeper.

    Output:
        Pandas Series with the blending factors for each cell item
    
    '''
    return 1/(1+np.exp(-(n-k)/f))

def target_encoding(df_train, feature, target, aggregate, kf_dict, hierarchy=None,):
    '''
    Target encoding using blending factor and accounting for hierarchy.
    
    Inputs :
            df_train : DataFrame used as the training set
            feature : string or list of strings representing all the features to take into account
            target : string indicating the target on which to do the encoding
            aggregate : callable (compatible with DataFrame) specifying which type of aggregation to perform (mean,median, sum, etc.)
            hirarchy : list of features to consider for upper hierarchy
    Outputs :
            dictionary where key = feature and value = target encoding
    '''
    # if feature is list, convert it to tuple
    if type(feature) is not str:
        feature = list(feature)
    
    # Compute the aggregate of the target variable for each category
    agg_by_feature = df_train.groupby(feature)[target].agg(aggregate).to_dict()
    
    # Compute the global aggregate
    agg = df_train[target].agg(aggregate)
    
    # Compute the counts for each category
    n = df_train.groupby(feature)[target].count()
    
    # Fetch k and f hyperparameters used in the blending function
    if type(feature) is not str:
        feature = tuple(feature)
    
    k,f = kf_dict.get(feature,(12,5))
    
    # Compute the blending factor
    lambda_factor = lambda_n(n,k,f).to_dict()
    
    # Compute target encoding
    if hierarchy == None:
        target_dict = {k: lambda_factor[k]*agg_by_feature[k] + (1-lambda_factor[k])*agg for k in lambda_factor}
    else:
        target_dict = {k: lambda_factor[k]*agg_by_feature[k] + (1-lambda_factor[k])*agg for k in lambda_factor}

    return target_dict

def clean_text(text):
    '''
    A function to remove stop words and special characters
    input :
        text as string
    Output:
        text as string
    '''
    # Remove special characters
    text = re.sub(r'[^\w\s]', '', text)
    # Convert to lowercase
    text = text.lower()
    # Remove stop words
    text = ' '.join([word for word in text.split() if word not in stop_words])
    return text

def process_batch(batch):
    '''
    Function to encode a single batch of texts
    Input: 
            texts : a sequence (Series, list, array, etc.) of strings
            
    Output:
            vecs : list of encoded vectors for each string
    '''
    
    vecs = []
    for doc in nlp.pipe(batch):
        if len(doc) > 0:
            vec = np.mean([word.vector for word in doc], axis=0)
            vecs.append(vec)
        else: 
            vecs.append(np.zeros(96))
    return np.vstack(vecs)

def encode_texts(texts, batch_size=1000):
    '''
    Function to encode many texts by batches
    Input: 
            texts : a sequence (Series, list, array, etc.) of strings 
            
    Output:
            vecs : list of encoded vectors for each string
    ''' 
    vecs = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        vecs.append(process_batch(batch))
    return np.vstack(vecs)

def compare_norm_dist(series,plots = True):
    '''
    This function takes a series as input and compares it to a normal distribution.
    It also returns the thresholds over which the distribution is not normal anymore.
    It was used to trim out outliers.
    
    Input:
        series : pandas.Series representing the data to compare with a normal
    
    Outputs:
        plots visualizations : histogram, box plot, and QQplot
        upper boundary:  float representing bound over which data is less than 3*std from the mean 
        lower boundary:  float representing bound over which data is less than 3*std from the mean
    
    '''
    # mean and standard deviation
    mu, std = norm.fit(series) 
    upper_boundary=mu + 2 * std
    lower_boundary=mu - 2 * std
    
    # Q1 = series.quantile(0.25)
    # Q3 = series.quantile(0.75)
    # IQR = Q3 - Q1
    # lower_boundary = Q1 - 1.5 * IQR
    # upper_boundary = Q3 + 1.5 * IQR
    

    if plots == True:
        # Plot the histogram.
        plt.hist(series, bins=25, density=True, alpha=0.6, color='orange', label='data')
        plt.axvline(upper_boundary,linestyle='dashed',linewidth='0.5', color='black',label='upper bound')
        plt.axvline(lower_boundary,linestyle='dashed',linewidth='0.5', color='black',label='lower bound')

        # Plot the PDF.
        xmin, xmax = plt.xlim()
        x = np.linspace(xmin, xmax, 100)
        p = norm.pdf(x, mu, std)

        plt.plot(x, p, 'k', linewidth=2,label='Theoretical normal')
        title = "Mean and Std Values: {:.2f} and {:.2f}".format(mu, std)
        plt.title(title)
        plt.legend()

        # Boxplot figure
        plt.figure()
        sns.boxplot(series)
        plt.axhline(upper_boundary,linestyle='dashed',linewidth='0.5', color='black',label='upper bound')
        plt.axhline(lower_boundary,linestyle='dashed',linewidth='0.5', color='black',label='lower bound')
        plt.legend()

        plt.figure()
        # Create a QQ-plot of the log_price variable
        fig, ax = plt.subplots()
        probplot(series, dist = 'norm', plot = ax)
        ax.set_title('QQ-plot of log_price')
        ax.set_xlabel('Theoretical quantiles')
        ax.set_ylabel('Sample quantiles')
        plt.axhline(upper_boundary,linestyle='dashed',linewidth='0.5', color='black',label='upper bound')
        plt.axhline(lower_boundary,linestyle='dashed',linewidth='0.5', color='black',label='lower bound')
        plt.legend()
    
    return upper_boundary,lower_boundary

def preprocess(file_path,test_size=0.12,random_state=100, do_pca=False):
    '''
    Fetches files in a given path and preprocess them to return a feature matrix X (dataframe) and target values y (dataframe)
    Input :
        files: path as string
        final_test_set: a boolean that is used only for the final test set
        test_size : size of the remaining test set
        random_state : random_state of the train/test split selection
        do_pca : If set to true, compute the name encoding and pca embeddings for 20 PC (computationally expensive)
    Outputs : 
        X_train : Train Feature matrix as DataFrame
        y_train : Train Target values as Series
        X_test : Test Feature matrix as DataFrame
        y_test : Test Target values as Series
    '''
    #Load file    
    df = pd.read_csv(file_path['data'])
    
    #Import external features from external source : https://public.opendatasoft.com/explore/dataset/airbnb-listings/export/?disjunctive.host_verifications&disjunctive.amenities&disjunctive.features&refine.city=New+York
    opendata_str = ['Name','Summary','Space', 'Description', 'Experiences Offered', 'Neighborhood Overview','Notes', 'Transit', 'Access', 'Interaction','Amenities','Bed Type']
    opendata_float = ['Host Response Rate','Accommodates','Bathrooms','Bedrooms','Beds','Square Feet']

    opendata = pd.read_csv(file_path['opendata'],sep=';',usecols=['ID']+opendata_str+opendata_float)
    opendata['text'] = opendata[opendata_str].fillna('').sum(axis=1)
    opendata[opendata_float]= opendata[opendata_float].fillna(-1)

    # Remove entries with no price
    df = df[df['price']!=0]
    df = df[df['availability_365']!=0]

    # Replace NaN values by 0
    df['number_of_reviews'].fillna(0, inplace=True)
    df['reviews_per_month'].fillna(0, inplace=True)
    df['name'].fillna('Unnamed', inplace=True)
    df['last_review'].fillna('1900-01-01',inplace=True)
    
    # Add external features
    df = df.merge(opendata[['ID','text']+opendata_float],how='left',left_on='id',right_on='ID')
    df[opendata_float]= df[opendata_float].fillna(-2)
    df[['ID','text']]= df[['ID','text']].fillna('Unknown')

    # Processing dates
    df['last_review'] = pd.to_datetime(df['last_review'])
    df['recency_last_review'] = (np.datetime64('today') - df['last_review']) / np.timedelta64(1, 'D')
    df['last_review_day'] = df['last_review'].dt.day
    df['last_review_month'] = df['last_review'].dt.month
    df['last_review_year'] = df['last_review'].dt.year
    
    #One hot encoding of 'room_type'
    neig= df['neighbourhood_group'].copy()
    df = pd.get_dummies(df, columns=['room_type','neighbourhood_group'])
    df['neighbourhood_group']= neig
    
    #Transform latitude and longitude in cartesian coordinates (x,y,z) (Earth as a 3D sphere and (0,0,0) its center)
    zone = df[['latitude','longitude']].to_numpy()
    x,y,z = get_cartesian(zone[:,0],zone[:,1])
    df= df.drop(['latitude','longitude'], axis=1)
    df['x'] = x
    df['y'] = y
    df['z'] = z
        
    # Encoding of the names of Airbnb postings using one of spaCy's pretrained model
    if do_pca:
        encoded_names = encode_texts(df['name'])

        # PCA embeddings of the  encoded vectors of the name of Airbnb postings
        pca = PCA()
        names_pca = pca.fit_transform(encoded_names)
        pca_df = pd.DataFrame(names_pca[:,:20],columns=['name_encoding_PC_'+str(i+1) for i in range(20)])
        pca_df.index = list(df.index)
        df = pd.concat((df,pca_df),axis=1)
    
    # TSNE embeddings of the  encoded vectors of the name of Airbnb postings AND of the texts (Description,) from external feature 
    name_tsne_df = pd.read_csv(file_path['name_tsne'],names = ['name_encoding_tsne_1','name_encoding_tsne_2'],skiprows=1)
    name_tsne_df.index = list(df.index)
    df = pd.concat((df,name_tsne_df),axis=1)
    
    text_tsne_df = pd.read_csv(file_path['text_tsne'],names = ['text_tsne_id','text_encoding_tsne_1','text_encoding_tsne_2'],skiprows=1)
    text_tsne_df.index = list(df.index)
    df = pd.concat((df,text_tsne_df),axis=1)
    
    # We trim out the outliers using the log log price distribution
    df['log_log_price'] = np.log(np.log(1+df['price']))

    # We compute the upper and lower thresholds
    u,l = compare_norm_dist(df['log_log_price'], False)

    # We keep only the datapoints within the thresholds
    df = df[(df['log_log_price']>l)&(df['log_log_price']<u)]
    
    # Processing categorical features with high cardinality through blended target encoding (mean and median)
    #df['log_price'] = np.log(1+df['price'])
    kf_dict = {'host_id':(3,0.5),'neighbourhood_group':(5,150),'neighbourhood':(25,9)}

    # Split is done before target encoding to prevent from data leakage
    X_train, X_test = train_test_split(df, test_size=test_size, random_state=random_state)
    X_train, X_val = train_test_split(X_train, test_size=test_size, random_state=random_state)

    # mean and median target encoding
    for feature in ['host_id','neighbourhood','neighbourhood_group',['host_id','neighbourhood']]:
        mean_target = target_encoding(X_train, feature, 'price', np.mean,kf_dict)
        median_target = target_encoding(X_train, feature, 'price', np.median,kf_dict)
        std_target = target_encoding(X_train, feature, 'price', np.std,kf_dict)
        
        if type(feature) is not list:
            X_train['mean_target_'+ str(feature)] = X_train[feature].map(mean_target)
            X_train['median_target_'+ str(feature)] = X_train[feature].map(median_target)
            X_train['std_target_'+ str(feature)] = X_train[feature].map(std_target)
            
            X_val['mean_target_'+ str(feature)] = X_val[feature].map(mean_target).fillna(X_train['price'].mean())
            X_val['median_target_'+ str(feature)] = X_val[feature].map(median_target).fillna(X_train['price'].median())
            X_val['std_target_'+ str(feature)] = X_val[feature].map(std_target).fillna(X_train['price'].std(ddof=0))
            
            X_test['mean_target_'+ str(feature)] = X_test[feature].map(mean_target).fillna(X_train['price'].mean())
            X_test['median_target_'+ str(feature)] = X_test[feature].map(median_target).fillna(X_train['price'].median())
            X_test['std_target_'+ str(feature)] = X_test[feature].map(std_target).fillna(X_train['price'].std(ddof=0))
        else:
            X_train['mean_target_'+ '_'.join(feature)] = X_train[feature].apply(lambda x: mean_target.get(tuple(x)),axis = 1)
            X_train['median_target_'+ '_'.join(feature)] = X_train[feature].apply( lambda x: median_target.get(tuple(x)),axis = 1)
            X_train['std_target_'+ '_'.join(feature)] = X_train[feature].apply( lambda x: std_target.get(tuple(x)),axis = 1)
            
            X_val['mean_target_'+ '_'.join(feature)] = X_val[feature].apply( lambda x: mean_target.get(tuple(x)),axis = 1).fillna(X_train['price'].mean())
            X_val['median_target_'+ '_'.join(feature)] = X_val[feature].apply( lambda x: median_target.get(tuple(x)),axis = 1).fillna(X_train['price'].median())
            X_val['std_target_'+ '_'.join(feature)] = X_val[feature].apply( lambda x: std_target.get(tuple(x)),axis = 1).fillna(X_train['price'].std(ddof=0))
            
            X_test['mean_target_'+ '_'.join(feature)] = X_test[feature].apply( lambda x: mean_target.get(tuple(x)),axis = 1).fillna(X_train['price'].mean())
            X_test['median_target_'+ '_'.join(feature)] = X_test[feature].apply( lambda x: median_target.get(tuple(x)),axis = 1).fillna(X_train['price'].median())
            X_test['std_target_'+ '_'.join(feature)] = X_test[feature].apply( lambda x: std_target.get(tuple(x)),axis = 1).fillna(X_train['price'].std(ddof=0))
            

            
    #Split the target variable from the features
    y_train = X_train['price']
    X_train= X_train.drop(['id','name','host_id','host_name','ID','text','text_tsne_id','neighbourhood_group', 'neighbourhood','last_review','price','log_log_price'], axis=1)
    y_val = X_val['price']
    X_val= X_val.drop(['id','name','host_id','host_name','ID','text','text_tsne_id','neighbourhood_group', 'neighbourhood','last_review','price','log_log_price'], axis=1)
    y_test = X_test['price']
    X_test= X_test.drop(['id','name','host_id','host_name','ID','text','text_tsne_id','neighbourhood_group', 'neighbourhood','last_review','price','log_log_price'], axis=1)

    return X_train, X_test, X_val, y_train, y_test, y_val


def scores(y_true,y_pred, plot=False):
    '''
    Compute MAE, MSE, RMSE, R2 and MAPE scores and plot prediction errors
    Inputs :
        y_true : true target values
        y_pred : predictions
        plot: if True plots errors
    Outputs:
        A score dictionary containing the computed metrics
    '''
    #Compute MAE, MSE, RMSE, R2 and MAPE scores
    mae = mean_absolute_error(y_true=y_true, y_pred=y_pred)
    mse = mean_squared_error(y_true=y_true, y_pred=y_pred)
    rmse = mean_squared_error(y_true=y_true, y_pred=y_pred, squared=False)
    r2 = r2_score(y_true=y_true, y_pred=y_pred)
    mape = mean_absolute_percentage_error(y_true=y_true, y_pred=y_pred)
    error_ratio_rmse = rmse/np.mean(y_true)
    error_ratio_mae = mae/np.mean(y_true)

    # Plot the obtained errors and residuals if plot argument is set to True
    if plot:
        fig, axs = plt.subplots(ncols=2,figsize=(15,5))
        x = [np.amin([y_true,y_pred]),np.amax([y_true,y_pred])]
        axs[0].scatter(y_pred,y_true,label="actual_vs_predicted")
        axs[0].plot(x,x,color='black',linestyle='dashed')
        axs[0].set_title("Actual vs. Predicted values")
        axs[0].set_ylabel("Actual")
        axs[0].set_xlabel("Predicted")
        axs[1].scatter(y_pred,y_true-y_pred,label="residual_vs_predicted")
        axs[1].plot(x,[0]*len(x),color='black',linestyle='dashed')
        axs[1].set_title("Residuals vs. Predicted Values")
        axs[1].set_ylabel("Residuals (Actuals-Predictions)")
        axs[1].set_xlabel("Predicted")
        fig.suptitle("Prediction errors")
        plt.show()

    # Print the scores
    print(f'R²: {r2}')
    print(f'MAE: {mae}')
    print(f'MSE: {mse}')
    print(f'RMSE: {rmse}')
    print(f'MAPE: {mape}')
    print(f'error_ratio_rmse: {error_ratio_rmse}')
    print(f'error_ratio_mae: {error_ratio_mae}')

    #Return the scores in a dictionary
    scores = {
            'R2': r2,
            'MAE': mae,
            'MSE': mse,
            'RMSE': rmse,
            'MAPE': mape,
            'error_ratio_rmse': error_ratio_rmse,
            'error_ratio_mae': error_ratio_mae,
            }

    return scores

def load_params(filename):
    '''
    load json files containing tuned models' parameters
    
    INPUT:
        filename: name of the json file as a string 
    
    OUTPUT:
        params:  dictionary containing the model's parameters
    '''
    with open(filename, 'r') as f:
        params = json.load(f)
    return params

def vote_prediction(estimators,X_train_np,y_train_np,X_test_np, weights = None):
    '''
    Homemade voting algorithm that computes predictions and make a weighted sum or average
    
    INPUTS:
        estimators : list of tuples containing a (string,model)
        X_train_np : training feature matrix as numpy array
        y_train_np : y labels for training
        X_test_np  : test feature matrix as numpy array
        
    OUTPUTS:
        y_pred : predicted labels
    '''

    # Initiate prediction vector
    y_pred = []

    # For all estimators append the predictions
    for est_name, estimator in estimators:
        y_pred.append(np.maximum(0,estimator.fit(X_train_np, y_train_np).predict(X_test_np)))
    
    if weights == None:
        # If weights are NOT specified, compute an average 
        y_pred = np.mean(y_pred, axis = 0)
    else:
        # If weights are specified, compute a weighted sum
        y_pred = np.sum([weights[i]*y_pred[i] for i in range(len(weights))],axis=0)

    return y_pred



def stacking_prediction(estimators,X_train_np,y_train_np,X_test_np, cv = 5):
    '''
    Homemade stacking algorithm - computes predictions on k-fold to feed a final metamodel (linear regression)
    
    INPUTS:
        estimators : list of tuples containing a (string,model)
        X_train_np : training feature matrix as numpy array
        y_train_np : y labels for training
        X_test_np  : test feature matrix as numpy array
        
    OUTPUTS:
        y_pred : predicted labels
    '''
    # Affect Cross validation indexes for each fold
    cv_idx = np.random.choice(np.arange(cv),size = X_train_np.shape[0])

    # Number of estimators
    n_estimators = len(estimators)
    
    # Initiate the meta feature matrix
    X_meta = np.zeros((X_train_np.shape[0],n_estimators))

    # For each fold compute predictions and fill in the meta feature matrix
    for i in range(cv):
        X_cv_train = X_train_np[cv_idx!=i,:]
        y_cv_train = y_train_np[cv_idx!=i]
        X_cv_val =  X_train_np[cv_idx==i,:]
        
        for j in range(n_estimators):
                X_meta[cv_idx==i,j] = np.maximum(0,estimators[j][1].fit(X_cv_train, y_cv_train).predict(X_cv_val))
    
    # Concatenate the meta feature matrix with the Initial feature matrix
    X_meta = np.concatenate((X_train_np,X_meta),axis=1)
    
    # Create the test meta feature Matrix (using whole train set) and concatenate it 
    X_meta_test = np.zeros((X_test_np.shape[0],n_estimators))
    for j in range(n_estimators):
        X_meta_test[:,j] = np.maximum(0,estimators[j][1].fit(X_train_np, y_train_np).predict(X_test_np))
    
    X_meta_test = np.concatenate((X_test_np,X_meta_test),axis=1)

    # Make a Final prediction using a final estimator (Linear Regression here)
    y_pred = LinearRegression().fit(X_meta,y_train_np).predict(X_meta_test)
    
    return y_pred
    

