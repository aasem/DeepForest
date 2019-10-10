#utility functions for demo
import os
import yaml
import sys
from tqdm import tqdm
import json
import pandas as pd
import numpy as np
import urllib
import xmltodict
import csv
from keras_retinanet import models

def label_to_name(label):
        """ Map label to name.
        """
        return "Tree"

def read_config():
        try:
                with open("deepforest_config.yml", 'r') as f:
                        config = yaml.load(f)
        except Exception as e:
                raise FileNotFoundError("There is no config file in dir:{}, yields {}".format(os.getcwd(),e))
                
        return config

def read_model(model_path, config):
        model = models.load_model(model_path, backbone_name='resnet50')
        return model

#Download progress bar
class DownloadProgressBar(tqdm):
        def update_to(self, b=1, bsize=1, tsize=None):
                if tsize is not None:
                        total = tsize
                update(b * bsize - n)
                
def use_release():
        '''
        Check the existance of, or download the latest model release from github
        
        Returns:
                output_path (str): path to downloaded model weights'''
        #Find latest github tag release from the DeepLidar repo
        _json = json.loads(urllib.request.urlopen(urllib.request.Request(
                'https://api.github.com/repos/Weecology/DeepForest/releases/latest',
            headers={'Accept': 'application/vnd.github.v3+json'},
             )).read())     
        asset = _json['assets'][0]
        output_path = os.path.join('data',asset['name'])    
        url = asset['browser_download_url']
        
        #Download if it doesn't exist
        if not os.path.exists(output_path):
                print("Downloading model from DeepForest release {}, see {} for details".format(_json["tag_name"],_json["html_url"]))                
                with DownloadProgressBar(unit='B', unit_scale=True,
                                     miniters=1, desc=url.split('/')[-1]) as t:
                        urllib.request.urlretrieve(url, filename=output_path, reporthook=t.update_to)           
        else:
                print("Model from DeepForest release {} was already downloaded. Loading model from file.".format(_json["html_url"]))
                
        return output_path

def xml_to_annotations(xml_path, rgb_dir):
        """
        Load annotations from xml format (e.g. RectLabel editor) and convert them into retinanet annotations format. 
        args:
                xml_path (str): Path to the annotations xml, formatted by RectLabel
                rgb_dir (str): Directory path to the rgb dir
        Returns:
                Annotations (pandas dataframe): in the format -> path/to/image.jpg,x1,y1,x2,y2,class_name
        """
        #parse
        with open(xml_path) as fd:
                doc = xmltodict.parse(fd.read())

        #grab xml objects
        try:
                tile_xml=doc["annotation"]["object"]
        except Exception as e:
                raise Exception("error {} for path {} with doc annotation{}".format(e, xml_path, doc["annotation"]))

        xmin=[]
        xmax=[]
        ymin=[]
        ymax=[]
        label=[]

        if type(tile_xml) == list:
                treeID=np.arange(len(tile_xml))

                #Construct frame if multiple trees
                for tree in tile_xml:
                        xmin.append(tree["bndbox"]["xmin"])
                        xmax.append(tree["bndbox"]["xmax"])
                        ymin.append(tree["bndbox"]["ymin"])
                        ymax.append(tree["bndbox"]["ymax"])
                        label.append(tree['name'])
        else:
                #One tree
                treeID=0

                xmin.append(tile_xml["bndbox"]["xmin"])
                xmax.append(tile_xml["bndbox"]["xmax"])
                ymin.append(tile_xml["bndbox"]["ymin"])
                ymax.append(tile_xml["bndbox"]["ymax"])
                label.append(tile_xml['name'])        

        rgb_name = os.path.basename(doc["annotation"]["filename"])
        
        annotations = pd.DataFrame({"image_path": rgb_name,"xmin":xmin,"ymin": ymin,"xmax":xmax, "ymax": ymax,"label":label})
        return(annotations)        

def create_classes(annotations_file):
        """
        Create a class list in the format accepted by keras retinanet
        args:
                annotations_file: an annotation csv in the retinanet format path/to/image.jpg,x1,y1,x2,y2,class_name
        returns:
                path to classes file
        """
        annotations = pd.read_csv(annotations_file, names=["image_path","xmin","ymin","xmax","ymax","label"])
        
        #get dir to place along file annotations
        dirname = os.path.split(annotations_file)[0]
        classes_path = os.path.join(dirname,"classes.csv")
        
        #get unique labels
        labels = annotations.label.unique()
        print("There are {} unique labels: {} ".format(labels.shape[0],list(labels))) 
        
        #write label
        with open(classes_path,'w') as csv_file:
                writer = csv.writer(csv_file)   
                for index, label in enumerate(labels):
                        writer.writerow([label, index])
        
        return classes_path

def number_of_images(annotations_file):
        """
        How many images in the annotations file
        Args:
                annotations_file (str):
        Returns:
                n (int): Number of images
        """
        df = pd.read_csv(annotations_file,names=["image_path","xmin","ymin","xmax","ymax"])
        n = len(df.image_path.unique())
        return n
        
def format_args(annotations, config):
        """Format config file to match argparse list for retinainet
        Args:
                config (dict): a dictionary object to convert into a list for argparse
        Returns:
                arg_list (list): a list structure that mimics argparse input arguments for retinanet
        """
        #Format args. Retinanet uses argparse, so they need to be passed as a list
        args = {}
        classes_file = create_classes(annotations)

        #remember that .yml reads None as a str
        if not config["weights"] == 'None':
                args["--snapshot"] = config["weights"]
                
        args["--backbone"] = config["backbone"]
        args["--image-min-side"] = config["image-min-side"]
        args["--multi-gpu"] = config["multi-gpu"]
        args["--epochs"] = config["epochs"]
        args["--steps"] = number_of_images(annotations)

        if args["--multi-gpu"] > 1:
                args["--multi-gpu-force"] = True

        #turn dictionary to list for argparse
        arg_list = [[k,v] for k, v in args.items()]
        arg_list = [val for sublist in arg_list for val in sublist]

        #positional arguments first
        arg_list =  arg_list + ["csv", annotations, classes_file] 

        #All need to be str classes to mimic sys.arg
        arg_list = [str(x) for x in arg_list]
        
        return arg_list