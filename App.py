import streamlit as st
import re
import nltk.corpus
from nltk.corpus import nps_chat
import pandas as pd
import pymysql
import logging
import requests
import facebook
from datetime import datetime
import threading 
import time
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from deep_translator import GoogleTranslator
import pyautogui

#Connection a la base de donne Nysql
connection = pymysql.connect(host='localhost',user='root',password='',db='facebookagent')
cursor = connection.cursor()



class RepeatedTimer(object):
  def __init__(self, interval, function, *args, **kwargs):
    self._timer = None
    self.interval = interval
    self.function = function
    self.args = args
    self.kwargs = kwargs
    self.is_running = False
    self.next_call = time.time()
    self.start()

  def _run(self):
    self.is_running = False
    self.start()
    self.function(*self.args, **self.kwargs)

  def start(self):
    if not self.is_running:
      self.next_call += self.interval
      self._timer = threading.Timer(self.next_call - time.time(), self._run)
      self._timer.start()
      self.is_running = True

  def stop(self):
    self._timer.cancel()
    self.is_running = False

def insert_page(id,nom,apropos,category):
    DB_table_name = 'page'
    insert_sql = "insert into " + DB_table_name + """
    values (%s,%s,%s,%s)"""
    rec_values = (id, nom, apropos, category)
    cursor.execute(insert_sql, rec_values)
    connection.commit()

def insert_post(id_post,type,message,created_time,id_page):
    DB_table_name = 'post'
    insert_sql = "insert into " + DB_table_name + """
    values (%s,%s,%s,%s,%s)"""
    rec_values = (id_post,type,message,created_time,id_page)
    cursor.execute(insert_sql, rec_values)
    connection.commit()

def insert_commentaire(id_commentaire,type,message,created_time,fk_id_post):
    DB_table_name = 'commentaire'
    insert_sql = "insert into " + DB_table_name + """
    values (%s,%s,%s,%s,%s)"""
    rec_values = (id_commentaire,type,message,created_time,fk_id_post)
    cursor.execute(insert_sql, rec_values)
    connection.commit()

def sentiment_scores(sentence):
 
    # Create a SentimentIntensityAnalyzer object.
    sid_obj = SentimentIntensityAnalyzer()
 
    # polarity_scores method of SentimentIntensityAnalyzer
    # object gives a sentiment dictionary.
    # which contains pos, neg, neu, and compound scores.
    sentiment_dict = sid_obj.polarity_scores(sentence)
 
    # decide sentiment as positive, negative and neutral
    if sentiment_dict['compound'] >= 0.05 :
        return "positive"
 
    elif sentiment_dict['compound'] <= -0.05 :
        return "negative"
 
    else :
        return "neutral"

class IsQuestion():
    
    # Init constructor
    def __init__(self):
        posts = self.__get_posts()
        feature_set = self.__get_feature_set(posts)
        self.classifier = self.__perform_classification(feature_set)
        
    # Method (Private): __get_posts
    # Input: None
    # Output: Posts (Text) from NLTK's nps_chat package
    def __get_posts(self):
        return nltk.corpus.nps_chat.xml_posts()
    
    # Method (Private): __get_feature_set
    # Input: Posts from NLTK's nps_chat package
    # Processing: 1. preserve alpha numeric characters, whitespace, apostrophe
    # 2. Tokenize sentences using NLTK's word_tokenize
    # 3. Create a dictionary of list of tuples for each post where tuples index 0 is the dictionary of words occuring in the sentence and index 1 is the class as received from nps_chat package 
    # Return: List of tuples for each post
    def __get_feature_set(self, posts):
        feature_list = []
        for post in posts:
            post_text = post.text            
            features = {}
            words = nltk.word_tokenize(post_text)
            for word in words:
                features['contains({})'.format(word.lower())] = True
            feature_list.append((features, post.get('class')))
        return feature_list
    
    # Method (Private): __perform_classification
    # Input: List of tuples for each post
    # Processing: 1. Divide data into 80% training and 10% testing sets
    # 2. Use NLTK's Multinomial Naive Bayes to perform classifcation
    # 3. Print the Accuracy of the model
    # Return: Classifier object
    def __perform_classification(self, feature_set):
        training_size = int(len(feature_set) * 0.1)
        train_set, test_set = feature_set[training_size:], feature_set[:training_size]
        classifier = nltk.NaiveBayesClassifier.train(train_set)
        print('Accuracy is : ', nltk.classify.accuracy(classifier, test_set))
        return classifier
        
    # Method (private): __get_question_words_set
    # Input: None
    # Return: Set of commonly occuring words in questions
    def __get_question_words_set(self):
        question_word_list = ['what', 'where', 'when','how','why','did','do','does','have','has','am','is','are','can','could','may','would','will','should'
"didn't","doesn't","haven't","isn't","aren't","can't","couldn't","wouldn't","won't","shouldn't",'?']
        return set(question_word_list)        
    
    # Method (Public): predict_question
    # Input: Sentence to be predicted
    # Return: 1 - If sentence is question | 0 - If sentence is not question
    def predict_question(self, text):
        words = nltk.word_tokenize(text.lower())        
        if self.__get_question_words_set().intersection(words) == False:
            return 0
        if '?' in text:
            return 1
        
        features = {}
        for word in words:
            features['contains({})'.format(word.lower())] = True            
        
        prediction_result = self.classifier.classify(features)
        if prediction_result == 'whQuestion' or prediction_result == 'ynQuestion':
            return 1
        return 0
    
    # Method (Public): predict_question_type
    # Input: Sentence to be predicted
    # Return: 'WH' - If question is WH question | 'YN' - If sentence is Yes/NO question | 'unknown' - If unknown question type
    def predict_question_type(self, text):
        words = nltk.word_tokenize(text.lower())                
        features = {}
        for word in words:
            features['contains({})'.format(word.lower())] = True            
        
        prediction_result = self.classifier.classify(features)
        if prediction_result == 'whQuestion':
            return 'WH'
        elif prediction_result == 'ynQuestion':
            return 'YN'
        else:
            return 'unknown'

def bot_work(app_id,app_secret,user_short_token,automatique_message):
    user_long_token = ""
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%d/%m/%y %H:%M:%S")
    url = "https://graph.facebook.com/oauth/access_token"    
    print(app_id,"\n",app_secret,"\n",user_short_token,"\n")
    payload = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": user_short_token,
    }
    try:
        response = requests.get(
            url,
            params=payload,
            timeout=5,
        )

    except requests.exceptions.Timeout as e:
        st.markdown('''<h2 style='text-align: left; color: #1ed760;'>Une erreur est survenue lors de l'execution du bot veuillez verifier la console pour plus de taille sur erreur \n Elle est generalement due a un probleme avec le user short code pense a le change et verifier votre connexion internet</h2>''',unsafe_allow_html=True)
        st.markdown('''<h1 style='text-align: left; color: #1ed760;'>Application vas etre reinitialiser dans 3 seconds veuillez verifier les informations avent de relance le bot Merc..</h1>''',unsafe_allow_html=True)
        logging.error("TimeoutError", e)
        time.sleep(3)
        pyautogui.hotkey("ctrl","F5")

    else:

        try:
            response.raise_for_status()

        except requests.exceptions.HTTPError as e:
            st.markdown('''<h2 style='text-align: left; color: #1ed760;'>Une erreur est survenue lors de l'execution du bot veuillez verifier la console pour plus de taille sur erreur \n Elle est generalement due a un probleme avec le user short code pense a le change et verifier votre connexion internet</h2>''',unsafe_allow_html=True)
            st.markdown('''<h1 style='text-align: left; color: #1ed760;'>Application vas etre reinitialiser dans 3 seconds veuillez verifier les informations avent de relance le bot Merc..</h1>''',unsafe_allow_html=True)
            logging.error("HTTPError", e)
            time.sleep(3)
            pyautogui.hotkey("ctrl","F5")

        else:
            try:
                response_json = response.json()
                logging.info(response_json)
                user_long_token = response_json["access_token"]
                graph = facebook.GraphAPI(access_token=user_long_token, version="3.1")
                pages_data = graph.get_object("/me/accounts")
                permanent_page_token = pages_data["data"][0]["access_token"]
                page_id = pages_data["data"][0]["id"]
                sql_select_Query = "select page.ID_page  from page where page.ID_page = '" + page_id + "'"
                cursor.execute(sql_select_Query)
                graph = facebook.GraphAPI(access_token=permanent_page_token, version="3.1")
                if cursor.rowcount == 0:
                    infos = graph.get_object(id=page_id, fields="category")
                    default_info = graph.get_object(id=page_id)
                    some_info = graph.get_object(id=page_id, fields='about, website')
                    insert_page(page_id,default_info['name'],some_info['about'],infos['category'])
                
                posts = graph.get_object(id=f'{page_id}/posts')
                for post in posts['data']:
                    post_id = post['id']
                    sql_select_Query = "select post.ID_post, post.post_message from post INNER JOIN page ON post.FK_ID_page = page.ID_page WHERE page.ID_page = '" + page_id  + "' and post.ID_post  = '" + post_id + "'"
                    cursor.execute(sql_select_Query)
                    comments = graph.get_object(id=f'{post_id}/comments')
                    if cursor.rowcount == 0:
                        if 'message' in post:
                            
                            insert_post(post_id,'message',post['message'],post['created_time'],page_id)
                        else:
                            if 'story' in post:
                                insert_post(post_id,'story',post['story'],post['created_time'],page_id)
                    for comment in comments['data']:
                        comment_id =  comment['id']
                        sql_select_Query = "select post.ID_post, post.post_message from post INNER JOIN page ON  post.FK_ID_page = page.ID_page INNER JOIN commentaire ON commentaire.FK_ID_post = post.ID_post WHERE page.ID_page = '" + page_id  + "' and post.ID_post  = '" + post_id + "' and commentaire.ID_commentaire = '" + comment_id + "'"
                        cursor.execute(sql_select_Query)
                        if cursor.rowcount == 0:
                            comment_message = GoogleTranslator(source='auto', target='en').translate(comment['message'])
                            comment_created_time = comment['created_time']
                            isQ = IsQuestion()
                            if isQ.predict_question(comment_message) :
                                insert_commentaire(comment_id,'question', comment_message, comment_created_time,post_id)
                                graph.put_comment(object_id=f'{comment_id}', message=automatique_message)
                            else:
                                if sentiment_scores(comment_message) == "positive":
                                    like = graph.get_object(id=f'{comment_id}/likes')
                                    if 'paging' not in like:
                                        graph.put_like(object_id=f'{comment_id}')
                                    insert_commentaire(comment_id,'positive', comment_message, comment_created_time,post_id)
                                elif sentiment_scores(comment_message) == "negative":
                                    insert_commentaire(comment_id,'negative', comment_message, comment_created_time,post_id)
                                elif sentiment_scores(comment_message) == "neutral":
                                    insert_commentaire(comment_id,'neutral', comment_message, comment_created_time,post_id)
            except:
                    st.markdown('''<h2 style='text-align: left; color: #1ed760;'>Une erreur est survenue lors de l'execution du bot veuillez verifier la console pour plus de taille sur erreur \n Elle est generalement due a un probleme avec le user short code pense a le change et verifier votre connexion internet</h2>''',unsafe_allow_html=True)
                    st.markdown('''<h1 style='text-align: left; color: #1ed760;'>Application vas etre reinitialiser dans 3 seconds veuillez verifier les informations avent de relance le bot Merc..</h1>''',unsafe_allow_html=True)
                    logging.error("Information Error", "Check App id, App secret and ")
                    time.sleep(3)
                    pyautogui.hotkey("ctrl","F5")

def run():
    st.title("Facebook Intelligent Agent Bot")
    # Create the DB
    db_sql = """CREATE DATABASE IF NOT EXISTS facebookagent;"""
    cursor.execute(db_sql)

    # Create table page
    DB_table_name_page = 'page'
    table_sql = "CREATE TABLE IF NOT EXISTS " + DB_table_name_page + """
                    (ID_page varchar(500) NOT NULL,
                     nom varchar(500) NOT NULL,
                     apropos VARCHAR(500) NOT NULL,
                     category VARCHAR(500) NOT NULL,
                     PRIMARY KEY (ID_page))ENGINE=InnoDB;
                    """
    cursor.execute(table_sql)


    # Create table post
    DB_table_name_post = 'post'
    table_sql = "CREATE TABLE IF NOT EXISTS " + DB_table_name_post + """
                    (ID_post varchar(500) NOT NULL,
                     post_type varchar(500) NOT NULL,
                     post_message VARCHAR(500) NOT NULL,
                     post_created_time VARCHAR(500) NOT NULL,
                     FK_ID_page varchar(500) NOT NULL,
                     PRIMARY KEY (ID_post),
                     FOREIGN KEY (FK_ID_page) REFERENCES """ + DB_table_name_page + """(ID_page))ENGINE=InnoDB;
                    """
    cursor.execute(table_sql)


    # Create table commentaire
    DB_table_name_comment = 'commentaire'
    table_sql = "CREATE TABLE IF NOT EXISTS " + DB_table_name_comment + """
                    (ID_commentaire varchar(500) NOT NULL,
                     commentaire_type varchar(500) NOT NULL,
                     commentaire_message VARCHAR(500) NOT NULL,
                     commentaire_created_time VARCHAR(500) NOT NULL,
                     FK_ID_post varchar(500) NOT NULL,
                     PRIMARY KEY (ID_commentaire),
                     FOREIGN KEY (FK_ID_post) REFERENCES """ + DB_table_name_post + """(ID_post))ENGINE=InnoDB;
                    """
    cursor.execute(table_sql)

    st.header("**App informations for Bot**")

    app_id = st.text_input("App ID")
    app_secret = st.text_input("App Secret")
    user_short_token = st.text_input("User Short Token")
    automatique_message = st.text_input("Message de reponse automatique")

    st.header("***Launch or Stop Bot***")

    timerexecusion = st.number_input("Duree en Minute avant rexecusion du bot", min_value=1)
    process_btn = st.button('START BOT') 
    if process_btn:
        if app_id == "":
            st.markdown('''<h4 style='text-align: left; color: red;'>App ID is empty''',unsafe_allow_html=True)
        if app_secret == "":
            st.markdown('''<h4 style='text-align: left; color: red;'>App Secret is empty''',unsafe_allow_html=True)
        if user_short_token == "":
            st.markdown('''<h4 style='text-align: left; color: red;'>User Shork Token is empty''',unsafe_allow_html=True)
        if app_id != "" and app_secret != "" and user_short_token != "":
            st.markdown('''<h4 style='text-align: left; color: #1ed760;'>Bot start correctly 🚀 Time : ''' + str(timerexecusion) + ''' Minute </h4>''',unsafe_allow_html=True)
            try:
                Myshudeler = RepeatedTimer(timerexecusion*60,bot_work,app_id,app_secret,user_short_token,automatique_message)
            except:
                st.markdown('''<h2 style='text-align: left; color: #1ed760;'>Une erreur est survenue lors de l'execution du bot veuillez verifier la console pour plus de taille sur erreur \n Elle est generalement due a un probleme avec le user short code pense a le change et verifier votre connexion internet</h2>''',unsafe_allow_html=True)
                st.markdown('''<h1 style='text-align: left; color: #1ed760;'>Application vas etre reinitialiser dans 3 seconds veuillez verifier les informations avent de relance le bot Merc..</h1>''',unsafe_allow_html=True)
                logging.error("Information Error", "Check App id, App secret and")
                time.sleep(3)
                pyautogui.hotkey("ctrl","F5")
            process_btn_ph = st.button('STOP BOT')
            if process_btn_ph:
                Myshudeler.stop()
                Myshudeler.stop()
                Myshudeler.stop()
                Myshudeler.stop()
                Myshudeler.stop()
                Myshudeler.stop()
                Myshudeler.stop()


        


    st.header("***Page Database Details***")
    datasetpage = {}
    sql_select_Query = "select page.ID_page, page.nom  from page"
    cursor.execute(sql_select_Query)
    if cursor.rowcount > 0:
        records = cursor.fetchall()
        for row in records:
            datasetpage[row[0]] = row[1]
        page_id = st.selectbox("Choice a page", list(datasetpage.keys()), format_func=datasetpage.get)
        # Select posts
        sql_select_Query = "select post.ID_post, post.post_message from post INNER JOIN page ON post.FK_ID_page = page.ID_page WHERE page.ID_page = '" + page_id + "'"
        cursor.execute(sql_select_Query)
        datasetposts = {}
        if cursor.rowcount > 0:
            records = cursor.fetchall()
            for row in records:
                datasetposts[row[0]] = row[1]
            post_id = st.selectbox("Choice a post", list(datasetposts.keys()), format_func=datasetposts.get)
            comment_type = st.selectbox('Choice a comment type',('question', 'positive', 'negative'))
            sql_select_Query = "select commentaire.commentaire_message from post INNER JOIN page ON  post.FK_ID_page = page.ID_page INNER JOIN commentaire ON commentaire.FK_ID_post = post.ID_post WHERE page.ID_page = '" + page_id  + "' and post.ID_post  = '" + post_id + "' and commentaire.commentaire_type = '" + comment_type + "'"
            cursor.execute(sql_select_Query)
            datasetcommentaire = list()
            if cursor.rowcount > 0:
                records = cursor.fetchall()
                for row in records:
                    datasetcommentaire.append(row[0])
                st.write("<br>".join(datasetcommentaire), unsafe_allow_html=True)
            else:
                st.markdown('''<h4 style='text-align: left; color: #1ed760;'>Aucun commentaire disponible pour ce post en base de donne pour le moment </h4>''',unsafe_allow_html=True)

        else :
            st.markdown('''<h4 style='text-align: left; color: #1ed760;'>Aucun post disponible pour cette page en base de donne pour le moment </h4>''',unsafe_allow_html=True)

    else:
        st.markdown('''<h4 style='text-align: left; color: #1ed760;'>Aucune page disponible en base de donnee pour le moment </h4>''',unsafe_allow_html=True)


run()