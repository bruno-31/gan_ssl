import tensorflow as tf


init_kernel = tf.random_normal_initializer(mean=0, stddev=0.05)


def leakyReLu(x, alpha=0.01, name=None):
    if name:
        with tf.variable_scope(name):
            return _leakyReLu_impl(x, alpha)
    else:
        return _leakyReLu_impl(x, alpha)

def _leakyReLu_impl(x, alpha):
    return tf.nn.relu(x) - (alpha * tf.nn.relu(-x))


# def get_getter(ema):
#     def  ema_getter(getter, name, *args, **kwargs):
#         var = getter(name, *args,**kwargs)
#         ema_var = ema.average(var)
#         return ema_var if ema_var else var
#     return ema_getter


def discriminator(inp, is_training, getter=None):
    # with tf.variable_scope('cls',custom_getter=getter):

    with tf.variable_scope('shared_weights',custom_getter=getter):
        x = tf.reshape(inp, [-1, 32, 32, 3])

        x = tf.layers.conv2d(x,64,[3,3],padding='SAME',kernel_initializer=init_kernel)
        x = tf.layers.batch_normalization(x,training=is_training)
        x = leakyReLu(x)
        x = tf.layers.conv2d(x,64,[3,3],padding='SAME',kernel_initializer=init_kernel)
        x = tf.layers.batch_normalization(x,training=is_training)
        x = leakyReLu(x)
        x = tf.layers.conv2d(x,64,[3,3],strides=2,padding='SAME',kernel_initializer=init_kernel)
        x = tf.layers.batch_normalization(x,training=is_training)
        x = leakyReLu(x)
        inter_layer3 = x

        # x = tf.layers.max_pooling2d(x,2,2,padding='SAME')
        x = tf.layers.dropout(x,0.5, training=is_training)

        x = tf.layers.conv2d(x,128,[3,3],padding='SAME',kernel_initializer=init_kernel)
        x = tf.layers.batch_normalization(x,training=is_training)
        x = leakyReLu(x)
        x = tf.layers.conv2d(x,128,[3,3],padding='SAME',kernel_initializer=init_kernel)
        x = tf.layers.batch_normalization(x,training=is_training)
        x = leakyReLu(x)
        x = tf.layers.conv2d(x,128,[3,3],strides=2,padding='SAME',kernel_initializer=init_kernel)
        x = tf.layers.batch_normalization(x,training=is_training)
        x = leakyReLu(x)
        inter_layer2 = x

        # x = tf.layers.max_pooling2d(x,2,2,padding='SAME')
        x = tf.layers.dropout(x,0.5, training=is_training)

        x = tf.layers.conv2d(x,128,[3,3],padding='VALID',kernel_initializer=init_kernel)
        x = tf.layers.batch_normalization(x,training=is_training)
        x = leakyReLu(x)
        x = tf.layers.conv2d(x,128,[1,1],padding='VALID',kernel_initializer=init_kernel)
        x = tf.layers.batch_normalization(x,training=is_training)
        x = leakyReLu(x)
        x = tf.layers.conv2d(x,128,[1,1],padding='VALID',kernel_initializer=init_kernel)
        x = tf.layers.batch_normalization(x,training=is_training)
        x = leakyReLu(x)
        inter_layer1 = x

        # x = tf.layers.average_pooling2d(x,pool_size=6,strides=1)
        x = tf.layers.max_pooling2d(x,pool_size=6,strides=4)
        x = tf.squeeze(x)

    with tf.variable_scope('cls_weights',custom_getter=getter):
        cls = tf.layers.dense(x,10,kernel_initializer=tf.random_normal_initializer(stddev=0.05))

    with tf.variable_scope('dis_weights'):
        dis = tf.layers.dense(x,1,kernel_initializer=tf.random_normal_initializer(stddev=0.05))

    return  cls,dis, inter_layer1 , inter_layer2, inter_layer3


def generator(z_seed, is_training):
    x = z_seed
    with tf.variable_scope('dense_1'):
        x = tf.layers.dense(x, units=4 * 4 * 512, kernel_initializer=init_kernel)
        x = tf.layers.batch_normalization(x, training=is_training, name='batchnorm_1')
        x = tf.nn.relu(x)

    x = tf.reshape(x, [-1, 4, 4, 512])

    with tf.variable_scope('deconv_1'):
        x = tf.layers.conv2d_transpose(x, 256, [5, 5], strides=[2, 2], padding='SAME', kernel_initializer=init_kernel)
        x = tf.layers.batch_normalization(x, training=is_training, name='batchnorm_2')
        x = tf.nn.relu(x)

    with tf.variable_scope('deconv_2'):
        x = tf.layers.conv2d_transpose(x, 128, [5, 5], strides=[2, 2], padding='SAME', kernel_initializer=init_kernel)
        x = tf.layers.batch_normalization(x, training=is_training, name='batchnormn_3')
        x = tf.nn.relu(x)

    with tf.variable_scope('deconv_3'):
        x = tf.layers.conv2d_transpose(x, 3, [5, 5], strides=[2, 2], padding='SAME', kernel_initializer=init_kernel)
        x = tf.nn.tanh(x)
    return x