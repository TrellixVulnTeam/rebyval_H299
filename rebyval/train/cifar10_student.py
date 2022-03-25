from sklearn import metrics
from tqdm import trange
import tensorflow as tf

# others
from rebyval.train.student import Student
from rebyval.tools.utils import print_warning, print_green, print_error, print_normal

class Cifar10Student(Student):
    
    def __init__(self, student_args, supervisor = None, id = 0):
        super(Cifar10Student, self).__init__(student_args, supervisor, id)


    # @tf.function(experimental_relax_shapes=True, experimental_compile=None)
    def _train_step(self, inputs, labels, train_step = 0, epoch=0):
        try:
            with tf.GradientTape() as tape:
                predictions = self.model(inputs, training=True)
                loss = self.loss_fn(labels, predictions)
            gradients = tape.gradient(loss, self.model.trainable_variables)
            self.optimizer.apply_gradients(
                zip(gradients, self.model.trainable_variables))
        except:
            print_error("train step error")
            raise
        
        with self.logger.as_default():
            step = train_step+epoch*self.dataloader.info['train_step']
            tf.summary.scalar("train_loss", loss, step=step)
            
        return loss

    # @tf.function(experimental_relax_shapes=True, experimental_compile=None)
    def _rebyval_train_step(self, inputs, labels, train_step = 0, epoch=0):
        try:
            with tf.GradientTape() as tape:
                predictions = self.model(inputs, training=True)
                s_loss = self.supervisor(self.model.trainable_variables)
                t_loss = self.loss_fn(labels, predictions)
                loss = t_loss + s_loss
            gradients = tape.gradient(loss, self.model.trainable_variables)
            self.optimizer.apply_gradients(
                zip(gradients, self.model.trainable_variables))
        except:
            print_error("rebyval train step error")
            raise
        
        with self.logger.as_default():
            step = train_step+epoch*self.dataloader.info['train_step']
            tf.summary.scalar("train_loss", t_loss, step=step)
            tf.summary.scalar("surrogate_loss", s_loss, step=step)
            
        return t_loss

    def _valid_step(self, inputs, labels, valid_step = 0, epoch=0, weight_space=None):
        try:
            self.metrics.reset_states()
            predictions = self.model(inputs, training=False)
            loss = self.loss_fn(labels, predictions)
            self.metrics.update_state(labels, predictions)
            metrics = self.metrics.result()
        except:
            print_error("valid step error")
            raise
        
        with self.logger.as_default():
            step = valid_step+epoch*self.dataloader.info['valid_step']
            tf.summary.scalar("valid_loss", loss, step=step)
            tf.summary.scalar("valid_metrics", metrics, step=step)
            
        return loss, metrics
    
    def _test_step(self, inputs, labels, test_step=0):
        try:
            predictions = self.model(inputs, training=False)
            loss = self.loss_fn(labels, predictions)
        except:
            print_error("test step error")
            raise
        
        with self.logger.as_default():
            tf.summary.scalar("test_loss", loss, step=test_step)
            
        return loss

    def train(self):
        # parse train loop control args
        train_loop_args = self.args['train_loop']
        train_args = train_loop_args['train']
        valid_args = train_loop_args['valid']
        test_args = train_loop_args['test']

        # dataset train, valid, test
        train_iter = iter(self.train_dataset)
        valid_iter = iter(self.valid_dataset)
        test_iter = iter(self.test_dataset)
        
        # metrics reset
        self.metrics.reset_states()

        # train, valid, write to tfrecords, test
        # tqdm update, logger
        with trange(self.dataloader.info['epochs'], desc="Epochs") as e:
            for epoch in e:
                with trange(self.dataloader.info['train_step'], desc="Train steps", leave=False) as t:
                    for train_step in t:
                        data = train_iter.get_next()
                        if self.supervisor == None:
                            train_loss = self._train_step(data['inputs'], data['labels'], 
                                                        train_step=train_step, epoch=epoch)
                        else:
                            train_loss = self._rebyval_train_step(data['inputs'], data['labels'], 
                                                        train_step=train_step, epoch=epoch)
                        t.set_postfix(train_loss=train_loss.numpy())
                        
                        if train_step % valid_args['valid_gap'] == 0:
                            with trange(self.dataloader.info['valid_step'], desc="Valid steps", leave=False) as v:
                                for valid_step in v:
                                    data = valid_iter.get_next()
                                    valid_loss, metrics= self._valid_step(data['inputs'], data['labels'],
                                                                  valid_step=valid_step, epoch=epoch, 
                                                                  weight_space=valid_args['weight_space'])
                                    v.set_postfix(valid_loss=valid_loss.numpy(), metric=metrics.numpy())
                                self._write_trace_to_tfrecord(weights = self.model.trainable_variables, 
                                                              valid_loss = valid_loss,
                                                              weight_space = valid_args['weight_space'])
                e.set_postfix(train_loss=train_loss.numpy(), valid_loss=valid_loss.numpy(), metric=metrics.numpy())
        
        with trange(self.dataloader.info['test_step'], desc="Test steps") as t:
            for test_step in t:
                data = test_iter.get_next()
                t_loss = self._test_step(data['inputs'], data['labels'], test_step = test_step)
                t.set_postfix(test_loss=t_loss.numpy())
                
        