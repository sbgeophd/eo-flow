import logging
import tensorflow as tf
from tensorflow.keras import layers
import numpy as np
from marshmallow import Schema, fields
from marshmallow.validate import OneOf, ContainsOnly

from ..base import BaseModel
from .layers import Conv2D, Deconv2D, CropAndConcat
from tensorflow.python.keras.engine import training_utils

import types

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

# Available losses
segmentation_losses = {
    'cross-entropy': tf.keras.losses.CategoricalCrossentropy(from_logits=True)
}

# Available metrics
segmentation_metrics = {
    'accuracy': tf.keras.metrics.CategoricalAccuracy(name='accuracy')
}

def cropped_loss(loss_fn):
    """ Wraps loss function. Crops the labels to match the logits size. """

    def _loss_fn(labels, logits):
        logits_shape = tf.shape(logits)
        labels_crop = tf.image.resize_with_crop_or_pad(labels, logits_shape[1], logits_shape[2])

        return loss_fn(labels_crop, logits)

    return _loss_fn

class CroppedMetric(tf.keras.metrics.Metric):
    """ Wraps a metric. Crops the labels to match the logits size. """

    def __init__(self, metric):
        super().__init__(name=metric.name, dtype=metric.dtype)
        self.metric = metric
    
    def update_state(self, y_true, y_pred, sample_weight=None):
        print(y_true, y_pred)
        logits_shape = tf.shape(y_pred)
        labels_crop = tf.image.resize_with_crop_or_pad(y_true, logits_shape[1], logits_shape[2])

        return self.metric.update_state(labels_crop, y_pred, sample_weight)      

    def result(self):
        return self.metric.result()

    def reset_states(self):
        return self.metric.reset_states()

    def get_config(self):
        return self.metric.get_config()

class BaseSegmentationModel(BaseModel):
    """ Base for segmentation models. """

    class _Schema(Schema):
        learning_rate = fields.Float(missing=None, description='Learning rate used in training.', example=0.01)
        loss = fields.String(missing='cross-entropy', description='Loss function used for training.',
                             validate=OneOf(segmentation_losses.keys()))
        metrics = fields.List(fields.String, missing=['accuracy'], description='List of metrics used for evaluation.',
                              validate=ContainsOnly(segmentation_metrics.keys()))

    def prepare(self):
        optimizer = tf.keras.optimizers.Adam(learning_rate=self.config.learning_rate)

        # Wrap loss function
        loss = self.config.loss
        if loss in segmentation_losses:
            loss = segmentation_losses[loss]
        wrapped_loss = cropped_loss(loss)

        # Wrap metrics
        metrics = self.config.metrics
        wrapped_metrics = []
        for metric in metrics:
            if metric in segmentation_metrics:
                metric = segmentation_metrics[metric]
                
            wrapped_metric = CroppedMetric(metric)
            wrapped_metrics.append(wrapped_metric)

        self.compile(optimizer=optimizer, loss=wrapped_loss, metrics=wrapped_metrics)
