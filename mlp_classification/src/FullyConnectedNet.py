import tensorflow as tf
import utils
from tensorflow.contrib.layers import fully_connected, l1_l2_regularizer
from tensorflow.contrib.slim import batch_norm
from tensorflow.python.ops import control_flow_ops
from configreader import get_task_sections


class FullyConnectedNet():
    """
        This employs a Softmax Classifier for multilabel classification
        We will employ a simple Softmax Model to classify the captions
    """

    def __init__(self, config):
        self.input_features_slicer = config.get_as_slice("FEATURES", "columns")

        self.l1_reg = [float(config["TRAINING"]["l1_regularization"])]
        self.l2_reg = [float(config["TRAINING"]["l1_regularization"])]
        self.num_hidden_units = int(config["NETWORK"]["layer_size"])
        self.num_layers = int(config["NETWORK"]["num_layers"])
        self.learning_rate = float(config["TRAINING"]["learning_rate"])

        self.optimizer = config["TRAINING"]["optimizer"]
        self.keep_prob = float(config["TRAINING"]["dropout_keep_probability"])

        self.config_task_sections = get_task_sections(config)

        self.add_placeholders()

    def make_hidden_FN_layers(self, input_layer):
        previous_out = input_layer

        with tf.variable_scope("hidden_layers"):
            for i in range(1, self.num_layers + 1):
                with tf.variable_scope("layer%d" % i) as layer_scope:
                    previous_out = fully_connected(previous_out, self.num_hidden_units, activation_fn=tf.nn.elu,
                                                   normalizer_fn=batch_norm,
                                                   normalizer_params={"scale": i == self.num_layers,
                                                                      "is_training": self.is_training,
                                                                      "decay": 0.9},
                                                   weights_regularizer=l1_l2_regularizer(self.l1_reg, self.l2_reg),
                                                   scope=layer_scope)

                    if i == self.num_layers:
                        previous_out = tf.nn.dropout(previous_out, self.keep_prob)

        last_hidden_layer = previous_out
        return last_hidden_layer

    def add_classification_output_layer(self, last_hidden_layer, gt_labels, num_classes, corpus_tag, task_tag):
        # returns loss op
        with tf.variable_scope("output_layer_%s" % task_tag) as layer_scope:
            last_out = fully_connected(last_hidden_layer, num_classes, activation_fn=tf.identity,
                                       weights_regularizer=l1_l2_regularizer(self.l1_reg, self.l2_reg),
                                       scope=layer_scope)
            self.predictions = tf.nn.softmax(last_out)

        with tf.name_scope("%s_loss_%s" % (corpus_tag, task_tag)):
            loss = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(last_out, gt_labels))
            utils.variable_summaries(loss, "loss", corpus_tag)

        with tf.name_scope('%s_accuracy_%s' % (corpus_tag, task_tag)):
            correct_prediction = tf.equal(tf.argmax(last_out, 1), gt_labels)
            accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32)) * 100
            utils.variable_summaries(accuracy, "accuracy", corpus_tag)
            self.calculate_accuracy_op = accuracy

        return loss

    def add_linear_output_layer(self, last_hidden_layer, ground_truth, corpus_tag, task_tag):
        # returns loss op
        with tf.variable_scope("output_layer_%s" % task_tag) as layer_scope:
            last_out = fully_connected(last_hidden_layer, 1, activation_fn=tf.identity,
                                       weights_regularizer=l1_l2_regularizer(self.l1_reg, self.l2_reg),
                                       scope=layer_scope)
            self.predictions = last_out

        with tf.name_scope("%s_loss_%s" % (corpus_tag, task_tag)):
            loss = tf.reduce_mean(tf.squared_difference(last_out, ground_truth))
            utils.variable_summaries(loss, "loss", corpus_tag)

        with tf.name_scope('%s_accuracy_%s' % (corpus_tag, task_tag)):
            accuracy = loss #meaningless
            utils.variable_summaries(accuracy, "accuracy_meaningless_", corpus_tag)
            self.calculate_accuracy_op = accuracy

        return loss

    def add_all_outputs_and_losses(self, input_features, input_data, corpus_tag):
        hidden_output = self.make_hidden_FN_layers(input_features)
        losses = tf.zeros([1])
        for task_name, task_config in self.config_task_sections.items():
            ground_truth = input_data[int(task_config["ground_truth_column"])]
            loss = None
            if task_config["type"] == "linear":
                task_name += "_lin"
                loss = self.add_linear_output_layer(hidden_output, ground_truth, corpus_tag, task_name)
            elif task_config["type"] == "classification":
                task_name += "_classf"
                num_classes = int(task_config["num_classes"])
                ground_truth = tf.to_int64(ground_truth)
                loss = self.add_classification_output_layer(hidden_output, ground_truth, num_classes, corpus_tag,
                                                            task_name)
            else:
                assert False
            losses = losses + loss
        self.loss_sum = losses


    def bind_graph(self, corpus_tag, input_data_rows, batch_size, reuse=False, with_training_op=False):
        # Builds all ops that correspond to the NN graph and its evaluators and optimizers.
        # Needs the input data Tensors/Queues as argument
        # Any of the built ops, e.g. self.loss,
        # operates on the input data (given as arguments to this function) every time it is called.
        # If reuse=True , the TF graph is not built, but simply reused from the memory with the most recent parameters.



        input_features = tf.reshape(tf.pack(input_data_rows[self.input_features_slicer]), [batch_size, -1])

        with tf.variable_scope("network", reuse=reuse):
            # self.Y_logits = self.make_FN_layers()
            self.add_all_outputs_and_losses(input_features,
                                            input_data_rows,
                                            corpus_tag)


            if with_training_op:
                self.updates_op = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
                self.loss = control_flow_ops.with_dependencies(tf.tuple(self.updates_op),
                                                               self.loss_sum)  # all losses
                self.train_op = self.add_optimizer(type=self.optimizer)
            else:
                self.loss = self.loss_sum
                # self.calculate_accuracy_op already done

            all_weight_vars = [tf.reshape(var, [-1]) for var in tf.get_collection(tf.GraphKeys.MODEL_VARIABLES) if "/weights" in var.name]
            tf.summary.histogram("weight_hist", tf.concat(0,all_weight_vars), collections=["%s_summaries" % corpus_tag])

            self.summaries_merged = self.get_summaries(corpus_tag)

    def add_placeholders(self):
        """
        Returns:
        """
        with tf.name_scope("Hypers"):
            self.keep_prob = tf.placeholder(dtype=tf.float32)
            self.is_training = tf.placeholder(dtype=tf.bool, shape=[])

    def add_optimizer(self, type="vanilla"):
        """
        Add the optimizer function to perform Gradient Descent
        Args:
            type: The type of update that is needed
                  ["vanilla", "adam", "adagrad", "rmsprop"]
        Returns: None
        """
        if type not in ["vanilla", "adam", "adagrad", "rmsprop"]:
            raise ValueError("Please provide any of [vanilla, adam, adagrad, rmsprop] for optimisation")

        with tf.name_scope("gradient_descent"):
            train_op = None
            if type == "vanilla":
                train_op = tf.train.GradientDescentOptimizer(self.learning_rate).minimize(self.loss)
            elif type == "adam":
                train_op = tf.train.AdamOptimizer(self.learning_rate).minimize(self.loss)
            elif type == "adagrad":
                train_op = tf.train.AdagradOptimizer(self.learning_rate).minimize(self.loss)
            elif type == "rmsprop":
                train_op = tf.train.RMSPropOptimizer(self.learning_rate).minimize(self.loss)
            return train_op

    def get_summaries(self, corpus_tag):

        return tf.summary.merge(tf.get_collection("%s_summaries" % corpus_tag))




