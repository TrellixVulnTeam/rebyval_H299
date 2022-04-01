import time
import argparse
import tensorflow as tf

from rebyval.tools.utils import *
from rebyval.controller.utils import *
from rebyval.train.cifar10_student import Cifar10Student
from rebyval.train.cifar10_supervisor import Cifar10Supervisor


class BaseController:
    def __init__(self, yaml_path=None):

        if yaml_path != None:
            print_normal("parse config from python script.")
            self.yaml_configs = get_yml_content(yaml_path)
        else:
            print_normal("parse config from command line.")
            command_args = self._args_parser()
            self.yaml_configs = get_yml_content(command_args.config)

        
        self.yaml_configs = check_args_from_input_config(self.yaml_configs)

        self._build_enviroment()
        
        self._student_ids = 0
        self._supervisor_ids = 0
        
        self.supervisor = self._build_supervisor()

    def _args_parser(self):
        parser = argparse.ArgumentParser('autosparsedl_config')
        parser.add_argument(
            '--config',
            type=str,
            default='./scripts/configs/cifar10/rebyval.yaml',
            help='yaml config file path')
        args = parser.parse_args()
        return args

    def _build_enviroment(self):
        self.args = self.yaml_configs['experiment']
        context = self.args['context']
        self.log_path = os.path.join(context['log_path'],context['name'])

    def _build_student(self, supervisor=None):
        student_args = self.args["student"]
        student_args['log_path'] = self.log_path
        student = Cifar10Student(student_args=student_args, 
                                 supervisor = supervisor,
                                 id = self._student_ids)
        self._student_ids += 1
        return student

    def _build_supervisor(self):
        supervisor_args = self.args["supervisor"]
        supervisor_args['log_path'] = self.log_path
        supervisor = Cifar10Supervisor(supervisor_args=supervisor_args,
                                       id = self._supervisor_ids)
        self._supervisor_ids += 1
        return supervisor
        
    def warmup(self, warmup):
        init_samples = warmup['student_nums']
        supervisor_trains = warmup['supervisor_trains']
        for i in range(init_samples):
            student = self._build_student()
            student.run()
        
        for j in range(supervisor_trains):
            keep_train = False if j == 0 else True
            self.supervisor.run(keep_train=keep_train, new_students=[])

    def main_loop(self):

        main_loop = self.args['main_loop']

        # init weights pool
        if 'warmup' in main_loop:
            self.warmup(main_loop['warmup'])

        # main loop
        for j in range(main_loop['nums']):
            new_student = []
            for i in range(main_loop['student_nums']):
                student = self._build_student(supervisor=self.supervisor)
                new_student.append(student.run())
            self.supervisor.run(keep_train=True, new_students=new_student)
            print_green("new_student:{}, welcome!".format(new_student))

    def run(self):
        
        print_green("Start to run!")
        
        self.main_loop()

        print_green('[Task Status]: Task done! Time cost: {:}')

    

