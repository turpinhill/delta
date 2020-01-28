import numpy as np
from numpy.lib.stride_tricks import as_strided

import tensorflow as tf

from delta.imagery import rectangle

def predict_array(model, cs, data, probabilities):
    out_shape = (data.shape[0] - cs + 1, data.shape[1] - cs + 1)
    chunks = as_strided(data, shape=(out_shape[0], out_shape[1], cs, cs, data.shape[2]),
                        strides=(data.strides[0], data.strides[1], data.strides[0],
                                 data.strides[1], data.strides[2]),
                        writeable=False)
    chunks = np.reshape(chunks, (-1, cs, cs, data.shape[2]))
    predictions = model.predict_on_batch(chunks)
    if not probabilities:
        best = np.argmax(predictions, axis=1)
        return np.reshape(best, (out_shape[0], out_shape[1]))
    return np.reshape(predictions, (out_shape[0], out_shape[1], predictions.shape[1]))

def predict_validate(model, cs, image, label, num_classes, input_bounds=None, probabilities=False, show_progress=False):
    """Like predict but returns (predicted image, error image, percent correct)."""
    block_size_x = 256
    block_size_y = 256

    # Set up the output image
    if not input_bounds:
        input_bounds = rectangle.Rectangle(0, 0, width=image.width(), height=image.height())

    if not probabilities:
        result = np.zeros((input_bounds.width() - cs + 1, input_bounds.height() - cs + 1), dtype=np.uint8)
    else:
        result = np.zeros((input_bounds.width() - cs + 1,
                           input_bounds.height() - cs + 1, num_classes), dtype=np.float32)
    errors = None
    confusion_matrix = None
    if label:
        errors = np.zeros((input_bounds.width() - cs + 1, input_bounds.height() - cs + 1), dtype=np.bool)
        confusion_matrix = np.zeros((num_classes, num_classes), dtype=np.int32)

    def callback_function(roi, data):
        image = predict_array(model, cs, data, probabilities)

        block_x = (roi.min_x - input_bounds.min_x) // block_size_x
        block_y = (roi.min_y - input_bounds.min_y) // block_size_y
        (sx, sy) = (block_x * block_size_x, block_y * block_size_y)
        if probabilities:
            result[sx : sx + image.shape[0], sy : sy + image.shape[1], :] = image
            image = np.argmax(image, axis=2)
        else:
            result[sx : sx + image.shape[0], sy : sy + image.shape[1]] = image
        if label:
            label_roi = rectangle.Rectangle(roi.min_x + (cs // 2), roi.min_y + (cs // 2),
                                            roi.max_x - (cs // 2), roi.max_y - (cs // 2))
            labels = np.squeeze(label.read(label_roi))
            errors[sx : sx + image.shape[0], sy : sy + image.shape[1]] = labels != image
            cm = tf.math.confusion_matrix(np.ndarray.flatten(labels), np.ndarray.flatten(image), num_classes)
            confusion_matrix[:, :] += cm

    output_rois = input_bounds.make_tile_rois(block_size_x + cs - 1, block_size_y + cs - 1,
                                              include_partials=True, overlap_amount=cs - 1)

    image.process_rois(output_rois, callback_function, show_progress=show_progress)
    return (result, errors, confusion_matrix)

def predict(model, cs, image, num_classes, input_bounds=None, probabilities=False, show_progress=False):
    """Returns the predicted image given a model, chunk size, and image."""
    return predict_validate(model, cs, image, None, num_classes, input_bounds, probabilities, show_progress)[0]
