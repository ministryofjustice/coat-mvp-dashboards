import random
import boto3
import awswrangler as wr

from config import ATHENA_REGION, ATHENA_OUTPUT_LOCATION, ATHENA_ROLE, ATHENA_WORKGROUP


class AthenaService:
    def __init__(self):
        self.workgroup = ATHENA_WORKGROUP
        self.region = ATHENA_REGION

        # Assume the IAM role
        credentials = boto3.client("sts", region_name=self.region).assume_role(
            RoleArn=ATHENA_ROLE,
            RoleSessionName=f"pod-athena-query-{random.randint(10 ** (5 - 1), (10**5) - 1)}",
        )["Credentials"]

        # Create a reusable boto3 Session
        self.session = boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=self.region,
        )

        identity = self.session.client("sts").get_caller_identity()
        print(f"Assumed identity: {identity['Arn']}")

        user_id = identity["UserId"]
        self.output_location = ATHENA_OUTPUT_LOCATION + user_id + "/"

    def run_query_to_df(self, database, query):
        """
        Runs an Athena query and returns the results directly as a Pandas DataFrame
        using awswrangler and Apache Arrow for maximum speed and memory efficiency.
        """
        print(f"Running optimized Athena query: {query}")

        # wr.athena.read_sql_query handles execution, waiting, and Arrow download automatically
        try:
            df = wr.athena.read_sql_query(
                sql=query,
                database=database,
                workgroup=self.workgroup,
                s3_output=self.output_location,
                boto3_session=self.session,
                ctas_approach=False
            )
        except Exception as e:
            print(f"Athena query execution failed: {e}")

        print(f"Query completed successfully. Loaded {len(df)} rows into DataFrame.")
        return df