import os
import re
import signal
import importlib
from openai import OpenAI
from .prompt_generator import CodePrompt

# Import the code module at first time, clear the content if error occured
import temp.code_solution  

class CodeGenerator:
    def __init__(self, ctx):
        
        self.code_dir = ctx.code_dir
        self.oai_model = ctx.openai_model
        self.logger = ctx.logger

        self.oai_client = OpenAI(**ctx.openai_cfg)
        self.query_generator = CodePrompt(ctx.code_mode, ctx.n_shot)
        
        self.temp_python_fp = os.path.join(ctx.temp_dir, "code_solution.py")
        self.py_block = r'```python\n(.*?)\n```'
    

    def generate_code(self, item):
        try:
            query = self.query_generator.get_prompt_by_mode(item)
        except ValueError as e:
            self.logger.error(f"Error when generating prompt: {e}")
            return None
        
        messages = [
            {"role": "system", "content": "You are a Python code generator based on the given instruction."},
            {"role": "user", "content": f"{query}\n\nYou are required to write an executable function that performs the task. The function input and output are both string. You must format the python code as below:\n\n```python\ndef solution(input):\n    # Coding here...\n    return output\n```"
            }
        ]

        try:
            completion = self.oai_client.chat.completions.create(
                model=self.oai_model,
                messages=messages,
                temperature=0.2
            )
            response = completion.choices[0].message.content
        except Exception as e:
            self.logger.error(f"Error when generating code: {e}")
            return False

        # Extract the code snippet from the response
        code_match = re.search(self.py_block, response, re.DOTALL)
        if code_match:
            code_snippet = code_match.group(1)
            # Verify that the code snippet contains a function definition
            if re.search(r'def\s+solution\s*\(', code_snippet):
                # Write the function to a temp file for execution
                with open(self.temp_python_fp, 'w') as f:
                    f.write(code_snippet)

                # store a copy of the code snippet in the code_fp
                self.save_code(self.code_dir, item['file_path'], code_snippet)

                return True

            else:
                self.logger.warning("Generated code does not contain a 'solution' function.")
                return False
        else:
            self.logger.warning("No Python code block found in the response.")
            return False

    
    def save_code(self, code_dir, file_path, code_snippet):
        # prepare the code file path
        dir_name, base_name = os.path.split(file_path)
        dir_name = os.path.join(code_dir, dir_name.replace('./data/', ''))
        os.makedirs(dir_name, exist_ok=True)
        
        base_name = os.path.splitext(base_name)[0] + '.py'
        code_fp = os.path.join(dir_name, base_name)

        with open(code_fp, 'w') as f:
            f.write(code_snippet)


    def execute_code(self, tests):
        try:
            # Attempt to reload the solution function
            solution_func = self._reload_func()
        except ImportError as e:
            self.logger.error(f"Import error:  {e}")
            return tests  # Return early if the import fails

        for t in tests:
            try:
                # Set the timeout handler, will stop the execution after 5 seconds, timeout! 
                signal.signal(signal.SIGALRM, self._timeout_handler)
                signal.alarm(5)  
                
                # Call the solution function
                func_output = solution_func(t['input'])
                t['code_output'] = func_output
                
                signal.alarm(0)  # Disable the alarm after successful execution
                
            except TimeoutError:
                self.logger.error(f"Timeout occurred for input: {t['input']}")
            except Exception as e:
                self.logger.error(f"Code solution error occurred: {e}")
            
        return tests

    # Reload the solution function
    def _reload_func(self):    
        importlib.reload(temp.code_solution)  # Reload the module
        from temp.code_solution import solution  # Import the updated solution function
        return solution
    
    # Define a timeout handler
    def _timeout_handler(self, signum, frame):
        raise TimeoutError("Function execution timed out")


    def run(self, item):
        self.logger.info(f"Generating code for {item['file_path']}")
        try:
            isCodeGen = self.generate_code(item)
        except Exception as e:
            self.logger.error(f"Error when generating code: {e}")
            isCodeGen = False
        
        # Execute code and evaluate result
        tests = [{'input': t['input'], 'output': t['output'], 'code_output': None} for t in item['tuples']]

        if isCodeGen:
            tests = self.execute_code(tests)
        
        return tests








