import tensorflow as tf
import datetime
from subprocess import Popen, PIPE, STDOUT
import os

def background_process(arg_list):
    try:
        from subprocess import DEVNULL # py3k
    except ImportError:
        import os
        DEVNULL = open(os.devnull, 'wb')

    Popen(arg_list, stdin=PIPE, stdout=DEVNULL, stderr=DEVNULL)

def make_it_hot(labels, num_classes):
    labels_fixed = tf.squeeze(tf.to_int64(labels))
    one_hot_labels = tf.one_hot(labels_fixed, num_classes, on_value=1, off_value=0)

    return one_hot_labels


def variable_summaries(var, name, collections_tag):
    """Attach a lot of summaries to a Tensor."""
    with tf.name_scope('%s_%s_summary' % (collections_tag, name)):
        tf.summary.scalar(name, var, collections=["%s_summaries" % collections_tag])


def date_time_string():
    return datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")



def mkdir_recursive(path):
    if not path:
        return
    sub_path = os.path.dirname(path)
    if not os.path.exists(sub_path):
        mkdir_recursive(sub_path)
    if not os.path.exists(path):
        os.mkdir(path)