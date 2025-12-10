"""
Airflow SSH Operator Example - Properly catching PHP script errors

This example shows how to configure an SSH operator to properly catch
errors from a PHP script running remotely.
"""

from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator
from airflow.operators.dummy import DummyOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'php_script_ssh_task',
    default_args=default_args,
    description='Run PHP script via SSH with proper error handling',
    schedule_interval=timedelta(hours=1),
    catchup=False,
)

# Solution 1: Wrap command in bash with exit code checking
# This ensures any error in the PHP script will cause the task to fail
php_task = SSHOperator(
    task_id='run_php_script',
    ssh_conn_id='your_ssh_connection_id',  # Configure this in Airflow Admin -> Connections
    command="""
        set -e  # Exit immediately if a command exits with a non-zero status
        set -o pipefail  # Return value of pipeline is last command with non-zero exit
        
        # Run PHP script and capture exit code
        php /path/to/your/script.php
        
        # Explicitly check exit code (redundant with set -e, but explicit)
        EXIT_CODE=$?
        if [ $EXIT_CODE -ne 0 ]; then
            echo "ERROR: PHP script failed with exit code $EXIT_CODE"
            exit $EXIT_CODE
        fi
        
        echo "SUCCESS: PHP script completed successfully"
    """,
    dag=dag,
)

# Solution 2: Alternative - Use bash -c with explicit error checking
php_task_alternative = SSHOperator(
    task_id='run_php_script_alt',
    ssh_conn_id='your_ssh_connection_id',
    command='bash -c "php /path/to/your/script.php || exit 1"',
    dag=dag,
)

# Solution 3: Use get_pty=True for better error propagation (if needed)
php_task_with_pty = SSHOperator(
    task_id='run_php_script_pty',
    ssh_conn_id='your_ssh_connection_id',
    command='php /path/to/your/script.php || exit 1',
    get_pty=True,  # Allocate pseudo-terminal for better error handling
    dag=dag,
)

start = DummyOperator(task_id='start', dag=dag)
end = DummyOperator(task_id='end', dag=dag)

start >> php_task >> end






