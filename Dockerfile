# Use the AWS base image for Python 3.12
FROM public.ecr.aws/lambda/python:3.12

# Install and build C++ Compiler
RUN microdnf update -y && microdnf install -y gcc-c++ make

# Copy requirements.txt
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install reqirements.txt
RUN pip install -r requirements.txt

# Copy function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}
COPY ./agents ${LAMBDA_TASK_ROOT}

# Set permissions
RUN chmod +x lambda_function.py

# Set CMD to handler
CMD ["lambda_function.lambda_handler"]