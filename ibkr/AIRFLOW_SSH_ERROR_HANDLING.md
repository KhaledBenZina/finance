# Airflow SSH Operator Error Handling Guide

## Problem
When using Airflow's SSH operator to run a PHP script remotely, the task shows as successful even when the PHP script fails. This happens because the SSH operator may not properly propagate exit codes from the remote command.

## Root Causes

1. **PHP script doesn't exit with non-zero code on failure** - PHP scripts that throw exceptions or errors might still exit with code 0
2. **Command wrapper doesn't check exit codes** - The SSH command might not be checking the exit status
3. **SSH operator configuration** - Missing parameters that ensure proper error propagation

## Solutions

### Solution 1: Wrap Command in Bash with Error Checking (Recommended)

Use `set -e` to make bash exit on any error, and explicitly check the exit code:

```python
php_task = SSHOperator(
    task_id='run_php_script',
    ssh_conn_id='your_ssh_connection_id',
    command="""
        set -e
        set -o pipefail
        php /path/to/your/script.php
        EXIT_CODE=$?
        if [ $EXIT_CODE -ne 0 ]; then
            echo "ERROR: PHP script failed with exit code $EXIT_CODE"
            exit $EXIT_CODE
        fi
        echo "SUCCESS: PHP script completed successfully"
    """,
    dag=dag,
)
```

**Why this works:**
- `set -e` makes bash exit immediately if any command fails
- `set -o pipefail` ensures pipelines fail if any command in the pipeline fails
- Explicit exit code check provides clear error messages

### Solution 2: Use Short-Circuit Operator

Simpler approach using `||` operator:

```python
php_task = SSHOperator(
    task_id='run_php_script',
    ssh_conn_id='your_ssh_connection_id',
    command='php /path/to/your/script.php || exit 1',
    dag=dag,
)
```

### Solution 3: Use get_pty Parameter

Allocate a pseudo-terminal which can help with error propagation:

```python
php_task = SSHOperator(
    task_id='run_php_script',
    ssh_conn_id='your_ssh_connection_id',
    command='php /path/to/your/script.php || exit 1',
    get_pty=True,  # Allocate pseudo-terminal
    dag=dag,
)
```

### Solution 4: Create a Wrapper Script

Create a bash wrapper script on the remote server that handles error checking:

**Remote script: `/path/to/run_php_with_checks.sh`**
```bash
#!/bin/bash
set -e
set -o pipefail

PHP_SCRIPT="/path/to/your/script.php"

echo "Starting PHP script: $PHP_SCRIPT"
php "$PHP_SCRIPT"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "SUCCESS: PHP script completed successfully"
    exit 0
else
    echo "ERROR: PHP script failed with exit code $EXIT_CODE"
    exit $EXIT_CODE
fi
```

**Airflow task:**
```python
php_task = SSHOperator(
    task_id='run_php_script',
    ssh_conn_id='your_ssh_connection_id',
    command='bash /path/to/run_php_with_checks.sh',
    dag=dag,
)
```

## Fixing the PHP Script

Ensure your PHP script exits with proper error codes:

### PHP Script Best Practices

```php
<?php
// Enable error reporting
error_reporting(E_ALL);
ini_set('display_errors', 1);

// Set error handler to exit on errors
set_error_handler(function($severity, $message, $file, $line) {
    error_log("PHP Error: $message in $file on line $line");
    exit(1);  // Exit with error code
});

// Set exception handler
set_exception_handler(function($exception) {
    error_log("PHP Exception: " . $exception->getMessage());
    exit(1);
});

try {
    // Your PHP code here
    $result = doSomething();
    
    if (!$result) {
        error_log("Operation failed");
        exit(1);  // Explicit exit on failure
    }
    
    echo "Success";
    exit(0);  // Explicit success exit
    
} catch (Exception $e) {
    error_log("Caught exception: " . $e->getMessage());
    exit(1);
}
?>
```

### Key PHP Points:
- Use `exit(1)` or `exit(255)` for errors (non-zero exit codes)
- Use `exit(0)` for success
- Catch exceptions and exit with error codes
- Log errors so they're visible in Airflow logs

## Testing Your Setup

### Test 1: Force PHP Script to Fail
Create a test PHP script that always fails:

```php
<?php
// test_fail.php
error_log("This is a test failure");
exit(1);
?>
```

Run it through your SSH operator - the task should **fail** in Airflow.

### Test 2: Force PHP Script to Succeed
Create a test PHP script that always succeeds:

```php
<?php
// test_success.php
echo "Success";
exit(0);
?>
```

Run it - the task should **succeed** in Airflow.

## Additional Recommendations

### 1. Enable Logging in SSH Operator
```python
php_task = SSHOperator(
    task_id='run_php_script',
    ssh_conn_id='your_ssh_connection_id',
    command='php /path/to/your/script.php || exit 1',
    do_xcom_push=True,  # Capture output in XCom if needed
    dag=dag,
)
```

### 2. Add Retry Logic
```python
php_task = SSHOperator(
    task_id='run_php_script',
    ssh_conn_id='your_ssh_connection_id',
    command='php /path/to/your/script.php || exit 1',
    retries=3,
    retry_delay=timedelta(minutes=5),
    dag=dag,
)
```

### 3. Use SSH Hook for Custom Logic
If you need more control, use SSHHook directly:

```python
from airflow.providers.ssh.hooks.ssh import SSHHook

def run_php_with_custom_checks(**context):
    ssh_hook = SSHHook(ssh_conn_id='your_ssh_connection_id')
    ssh_client = ssh_hook.get_conn()
    
    stdin, stdout, stderr = ssh_client.exec_command(
        'php /path/to/your/script.php'
    )
    
    exit_code = stdout.channel.recv_exit_status()
    
    if exit_code != 0:
        error_output = stderr.read().decode()
        raise Exception(f"PHP script failed with exit code {exit_code}: {error_output}")
    
    return stdout.read().decode()

php_task = PythonOperator(
    task_id='run_php_script',
    python_callable=run_php_with_custom_checks,
    dag=dag,
)
```

## Debugging Tips

1. **Check Airflow logs** - Look for the actual exit code in task logs
2. **Test command manually** - SSH into the remote server and run the command directly
3. **Check PHP error logs** - Ensure PHP errors are being logged somewhere accessible
4. **Verify SSH connection** - Test the SSH connection in Airflow UI (Admin -> Connections)

## Quick Fix for Existing DAG

If you have an existing DAG that's not catching errors, change:

```python
# BEFORE (won't catch errors)
command='php /path/to/script.php'
```

To:

```python
# AFTER (will catch errors)
command='php /path/to/script.php || exit 1'
```

Or:

```python
# BETTER (more robust)
command='set -e; php /path/to/script.php'
```

## Summary

The most reliable solution is to:
1. Wrap your PHP command in bash with `set -e` and explicit exit code checking
2. Ensure your PHP script exits with non-zero codes on failure
3. Use `|| exit 1` as a fallback if bash settings don't work in your environment

This ensures that any failure in the PHP script will be properly propagated to Airflow, causing the task to fail as expected.






