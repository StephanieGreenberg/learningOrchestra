from pyspark.sql import SparkSession
import os
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from pyspark.ml import Pipeline
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml.feature import HashingTF, Tokenizer, VectorAssembler
from pyspark.ml.tuning import CrossValidator, ParamGridBuilder
from pymongo import MongoClient

SPARKMASTER_HOST = "SPARKMASTER_HOST"
SPARKMASTER_PORT = "SPARKMASTER_PORT"
SPARK_DRIVER_PORT = "SPARK_DRIVER_PORT"
MODEL_BUILDER_HOST_NAME = "MODEL_BUILDER_HOST_NAME"


class ModelBuilderInterface():
    def build_model(self, database_url_training, database_url_test, label):
        pass


class DatabaseInterface():
    def get_filenames(self):
        pass


class RequestValidatorInterface():
    MESSAGE_INVALID_TRAINING_FILENAME = "invalid_training_filename"
    MESSAGE_INVALID_TEST_FILENAME = "invalid_test_filename"

    def training_filename_validator(self, training_filename):
        pass

    def test_filename_validator(self, test_filename):
        pass


class SparkModelBuilder(ModelBuilderInterface):
    METADATA_DOCUMENT_ID = 0
    DOCUMENT_ID_NAME = "_id"

    def __init__(self):
        self.spark_session = SparkSession \
            .builder \
            .appName("model_builder") \
            .config("spark.driver.port",
                    os.environ[SPARK_DRIVER_PORT]) \
            .config("spark.driver.host",
                    os.environ[MODEL_BUILDER_HOST_NAME])\
            .config('spark.jars.packages',
                    'org.mongodb.spark:mongo-spark' +
                    '-connector_2.11:2.4.2')\
            .master("spark://" +
                    os.environ[SPARKMASTER_HOST] +
                    ':' + str(os.environ[SPARKMASTER_PORT])) \
            .getOrCreate()

    def file_processor(self, database_url):
        file = self.spark_session.read.format("mongo").option(
            "uri", database_url).load()

        file_without_metadata = file.filter(
            file[self.DOCUMENT_ID_NAME] != self.METADATA_DOCUMENT_ID)

        metadata_fields = [
            "_id", "fields", "filename", "finished", "time_created", "url"]
        processed_file = file_without_metadata.drop(*metadata_fields)

        return processed_file

    def fields_from_dataframe(self, dataframe, is_string):
        text_fields = []
        first_row = dataframe.first()

        if(is_string):
            for column in dataframe.schema.names:
                if(type(first_row[column]) == str):
                    text_fields.append(column)
        else:
            for column in dataframe.schema.names:
                if(type(first_row[column]) != str):
                    text_fields.append(column)

        return text_fields

    def build_model(self, database_url_training, database_url_test,
                    label='label'):
        training_file = self.file_processor(database_url_training)

        pre_processing_text = list()
        assembler_columns_input = []

        training_string_fields = self.fields_from_dataframe(
            training_file, True)
        for column in training_string_fields:
            tokenizer = Tokenizer(
                inputCol=column, outputCol=(column + "_words"))
            pre_processing_text.append(tokenizer)

            hashing_tf_output_column_name = column + "_features"

            hashing_tf = HashingTF(
                            inputCol=tokenizer.getOutputCol(),
                            outputCol=hashing_tf_output_column_name)
            pre_processing_text.append(hashing_tf)
            assembler_columns_input.append(hashing_tf_output_column_name)

        training_number_fields = self.fields_from_dataframe(
            training_file, False)

        for column in training_number_fields:
            if(column != label):
                assembler_columns_input.append(column)

        assembler = VectorAssembler(
            inputCols=assembler_columns_input,
            outputCol="features")

        logistic_regression = LogisticRegression(maxIter=10)

        pipeline = Pipeline(
            stages=[*pre_processing_text, assembler, logistic_regression])
        param_grid = ParamGridBuilder().build()
        cross_validator = CrossValidator(
                            estimator=pipeline,
                            estimatorParamMaps=param_grid,
                            evaluator=BinaryClassificationEvaluator(),
                            numFolds=2)
        cross_validator_model = cross_validator.fit(training_file)

        test_file = self.file_processor(database_url_test)
        prediction = cross_validator_model.transform(test_file)

        for row in prediction.collect():
            print(row, flush=True)


class MongoOperations(DatabaseInterface):

    def __init__(self, database_url, database_port, database_name):
        self.mongo_client = MongoClient(
            database_url, int(database_port))
        self.database = self.mongo_client[database_name]

    def get_filenames(self):
        return self.database.list_collection_names()


class ModelBuilderRequestValidator(RequestValidatorInterface):
    def __init__(self, database_connector):
        self.database = database_connector

    def training_filename_validator(self, training_filename):
        filenames = self.database.get_filenames()

        if(training_filename not in filenames):
            raise Exception(self.MESSAGE_INVALID_TRAINING_FILENAME)

    def test_filename_validator(self, test_filename):
        filenames = self.database.get_filenames()

        if(test_filename not in filenames):
            raise Exception(self.MESSAGE_INVALID_TEST_FILENAME)