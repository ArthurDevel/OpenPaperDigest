import pendulum
from airflow.decorators import dag, task

@dag(
    dag_id="hello_world",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    tags=["example"],
    doc_md="""
    ### Hello World DAG

    This is a simple example DAG to demonstrate the basic structure of an Airflow workflow.
    It contains a single task that prints "Hello, World!".
    """,
)
def hello_world_dag():
    @task
    def print_hello():
        """
        This task simply prints "Hello, World!" to the logs.
        """
        print("Hello, World!")

    print_hello()

hello_world_dag()
