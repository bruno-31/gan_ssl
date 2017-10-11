import os
import time
import numpy as np
import tensorflow as tf
from mnist_chi_gan import generator, discriminator
from conv_model_improved import *

flags = tf.app.flags
FLAGS = flags.FLAGS
flags.DEFINE_integer("batch_size", 100, "batch size [100]")
flags.DEFINE_string('data_dir', './data/cifar-10-python', 'data directory')
flags.DEFINE_string('logdir', './log', 'log directory')
flags.DEFINE_integer('seed', 146, 'seed')
flags.DEFINE_integer('seed_data', 646, 'seed data')
flags.DEFINE_integer('seed_tf', 646, 'tf random seed')
flags.DEFINE_integer('labeled', 10, 'labeled image per class[100]')
flags.DEFINE_float('learning_rate_d', 0.00003, 'learning_rate dis[0.003]')
flags.DEFINE_float('learning_rate_g', 0.00003, 'learning_rate gen[0.003]')
flags.DEFINE_float('unl_weight', 0., 'unlabeled weight [1.]')
flags.DEFINE_float('lbl_weight', 1, 'labeled weight [1.]')
flags.DEFINE_float('cat_gen_weight', 0., 'categorical generator weight [1.]')
flags.DEFINE_integer('freq_print', 100, 'image summary frequency [100]')

FLAGS._parse_flags()
print("\nParameters:")
for attr, value in sorted(FLAGS.__flags.items()):
    print("{}={}".format(attr.lower(), value))
print("")


def sigmoid(logits, labels):
    return   -tf.reduce_sum(labels * tf.log(logits + 1e-10))


def main(_):
    if not os.path.exists(FLAGS.logdir):
        os.mkdir(FLAGS.logdir)

    # Random seed
    rng = np.random.RandomState(FLAGS.seed)  # seed labels
    rng_data = np.random.RandomState(FLAGS.seed_data)  # seed shuffling
    tf.set_random_seed(FLAGS.seed_tf)
    print('loading data')
    # load MNIST data
    data = np.load('../data/mnist.npz')
    trainx = np.concatenate([data['x_train'], data['x_valid']], axis=0).astype(np.float32)
    trainx_unl = trainx.copy()
    trainx_unl2 = trainx.copy()
    trainy = np.concatenate([data['y_train'], data['y_valid']]).astype(np.int32)
    nr_batches_train = int(trainx.shape[0] / FLAGS.batch_size)
    testx = data['x_test'].astype(np.float32)
    testy = data['y_test'].astype(np.int32)
    nr_batches_test = int(testx.shape[0] / FLAGS.batch_size)

    # select labeled data
    inds = rng_data.permutation(trainx.shape[0])
    trainx = trainx[inds]
    trainy = trainy[inds]
    txs = []
    tys = []
    for j in range(10):
        txs.append(trainx[trainy == j][:FLAGS.labeled])
        tys.append(trainy[trainy == j][:FLAGS.labeled])
    txs = np.concatenate(txs, axis=0)
    tys = np.concatenate(tys, axis=0)
    print('labeled digits : ', len(tys))

    '''construct graph'''
    print('constructing graph')
    inp = tf.placeholder(tf.float32, [FLAGS.batch_size, 28 * 28], name='labeled_data_input_pl')
    unl = tf.placeholder(tf.float32, [FLAGS.batch_size, 28 * 28], name='unlabeled_data_input_pl')
    lbl = tf.placeholder(tf.int32, [FLAGS.batch_size], name='lbl_input_pl')
    is_training_pl = tf.placeholder(tf.bool, [], name='is_training_pl')
    acc_train_pl = tf.placeholder(tf.float32, [], 'acc_train_pl')
    acc_test_pl = tf.placeholder(tf.float32, [], 'acc_test_pl')

    gen = generator
    dis = discriminator

    with tf.variable_scope('generator_model'):
        gen_inp, lbl_fake = gen(batch_size=FLAGS.batch_size, is_training=is_training_pl)

    with tf.variable_scope('discriminator_model') as scope:
        dis(inp, is_training_pl, init=True)  # Data driven initialization
        scope.reuse_variables()
        _, logits_cls_lab, _ = dis(inp, is_training_pl)
        logits_dis_unl, _, layer_real = dis(unl, is_training_pl)
        logits_dis_gen, logits_cls_gen, layer_fake = dis(gen_inp, is_training_pl)

    with tf.variable_scope("model_test") as test_scope:
        dis(inp, is_training_pl, True)
        test_scope.reuse_variables()
        logits_test, _, _ = dis(inp, is_training_pl, False)

    with tf.name_scope('loss_functions'):
        xentropy = tf.nn.sparse_softmax_cross_entropy_with_logits
        # sigmoid = tf.nn.sigmoid_cross_entropy_with_logits
        loss_cls = tf.reduce_mean(xentropy(logits=logits_cls_lab, labels=lbl))
        loss_dis_unl = tf.reduce_mean(sigmoid(logits=logits_dis_unl, labels=tf.ones([FLAGS.batch_size,1])))
        loss_dis_gen = tf.reduce_mean(sigmoid(logits=logits_dis_gen, labels=tf.zeros([FLAGS.batch_size,1])))
        loss_dis = loss_dis_unl + loss_dis_gen
        print1 = tf.Print(unl, [logits_dis_unl])
        print2 = tf.Print(inp, [logits_cls_lab])
        print3 = tf.Print(unl, [logits_dis_gen])
        print4 = tf.Print(unl, [logits_cls_gen])

        m1 = tf.reduce_mean(layer_real, axis=0)
        m2 = tf.reduce_mean(layer_fake, axis=0)
        loss_features_matching = tf.reduce_mean(tf.square(m1 - m2))
        loss_cat_gen = tf.reduce_mean(xentropy(logits=logits_cls_gen, labels=lbl_fake))
        loss_gen = loss_features_matching + FLAGS.cat_gen_weight * loss_cat_gen

        loss_gen = tf.clip_by_value(loss_gen, 1e8, 1e-6)
        loss_cls = tf.clip_by_value(loss_cls, 1e8, 1e-6)
        loss_dis = tf.clip_by_value(loss_dis, 1e8, 1e-6)

        accuracy_dis_unl = tf.reduce_mean(tf.cast(tf.greater(logits_dis_unl, 0), tf.float32))
        accuracy_dis_gen = tf.reduce_mean(tf.cast(tf.less(logits_dis_gen, 0), tf.float32))
        accuracy_dis = 0.5 * accuracy_dis_unl + 0.5 * accuracy_dis_gen
        fool_rate = tf.reduce_mean(tf.cast(tf.greater(logits_dis_gen, 0), tf.float32))

        correct_pred = tf.equal(tf.cast(tf.argmax(logits_cls_lab, 1), tf.int32), tf.cast(lbl, tf.int32))
        accuracy_cls = tf.reduce_mean(tf.cast(correct_pred, tf.float32))
        correct_pred_test = tf.equal(tf.cast(tf.argmax(logits_test, 1), tf.int32), tf.cast(lbl, tf.int32))
        accuracy_cls_test = tf.reduce_mean(tf.cast(correct_pred_test, tf.float32))

    with tf.name_scope('optimizers'):
        # control op dependencies for batch norm and trainable variables
        tvars = tf.trainable_variables()
        dvars = [var for var in tvars if 'discriminator_model' in var.name]
        cvars = [var for var in tvars if 'classifier_model' in var.name]
        gvars = [var for var in tvars if 'generator_model' in var.name]
        testvars = [var for var in tvars if 'model_test' in var.name]
        update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        update_ops_gen = [x for x in update_ops if ('generator_model' in x.name)]

        optimizer_cls = tf.train.AdamOptimizer(learning_rate=FLAGS.learning_rate_d, beta1=0.5, name='cls_optimizer')
        optimizer_dis = tf.train.AdamOptimizer(learning_rate=FLAGS.learning_rate_d, beta1=0.5, name='dis_optimizer')
        optimizer_gen = tf.train.AdamOptimizer(learning_rate=FLAGS.learning_rate_g, beta1=0.5, name='gen_optimizer')

        train_dis_op = optimizer_dis.minimize(loss_dis, var_list=dvars)
        train_cls_op = optimizer_cls.minimize(loss_cls, var_list=dvars)
        ema = tf.train.ExponentialMovingAverage(decay=0.9999) # moving average for testing
        maintain_averages_op = ema.apply(dvars)
        with tf.control_dependencies([train_cls_op]):
            train_cls_op_ema = tf.group(maintain_averages_op)
        copy_graph = [tf.assign(x, ema.average(y)) for x, y in zip(testvars, dvars)]
        with tf.control_dependencies(update_ops_gen):
            train_gen_op = optimizer_gen.minimize(loss_gen, var_list=gvars)

    with tf.name_scope('summary'):
        with tf.name_scope('dis_summary'):
            tf.summary.scalar('loss_dis', loss_dis, ['dis'])
            tf.summary.scalar('loss_dis_unl', loss_dis_unl, ['dis'])
            tf.summary.scalar('loss_dis_gen', loss_dis_gen, ['dis'])
            tf.summary.scalar('discriminator_accuracy', accuracy_dis, ['dis'])
            tf.summary.scalar('discriminator_accuracy_gen_samples', accuracy_dis_gen, ['dis'])
            tf.summary.scalar('discriminator_accuracy_unl_samples', accuracy_dis_unl, ['dis'])

        with tf.name_scope('cls_summary'):
            tf.summary.scalar('loss_cls', loss_cls, ['cls'])
            tf.summary.scalar('classifier_accuracy', accuracy_cls, ['cls'])


        with tf.name_scope('gen_summary'):
            tf.summary.scalar('loss_generator', loss_gen, ['gen'])
            tf.summary.scalar('fool_rate', fool_rate, ['gen'])

        with tf.name_scope('epoch_summary'):
            tf.summary.scalar('accuracy_train', acc_train_pl, ['epoch'])
            tf.summary.scalar('accuracy_test', acc_test_pl, ['epoch'])

        with tf.name_scope('image_summary'):
            tf.summary.image('gen_digits', tf.reshape(gen_inp, [-1, 28, 28, 1]), 20, ['image'])
            tf.summary.image('input_image', tf.reshape(unl, [-1,28,28,1]),10,['image'])

        sum_op_cls = tf.summary.merge_all('cls')
        sum_op_dis = tf.summary.merge_all('dis')
        sum_op_gen = tf.summary.merge_all('gen')
        sum_op_im = tf.summary.merge_all('image')
        sum_op_epoch = tf.summary.merge_all('epoch')

    check_op = tf.add_check_numerics_ops()
    '''//////perform training //////'''
    print('start training\n')
    with tf.Session() as sess:
        init = tf.global_variables_initializer()
        # Data-Dependent Initialization of Parameters as discussed in DP Kingma and Salimans Paper
        sess.run(init, feed_dict={inp: trainx_unl[0:FLAGS.batch_size], is_training_pl: True})
        writer = tf.summary.FileWriter(FLAGS.logdir, sess.graph)
        batch = 0
        print('initialization done')

        for epoch in range(200):
            begin = time.time()

            # construct randomly permuted minibatches
            trainx = []
            trainy = []
            for t in range(int(np.ceil(trainx_unl.shape[0] / float(txs.shape[0])))):  # same size lbl and unlb
                inds = rng.permutation(txs.shape[0])
                trainx.append(txs[inds])
                trainy.append(tys[inds])
            trainx = np.concatenate(trainx, axis=0)
            trainy = np.concatenate(trainy, axis=0)
            trainx_unl = trainx_unl[rng.permutation(trainx_unl.shape[0])]  # shuffling unl dataset
            trainx_unl2 = trainx_unl2[rng.permutation(trainx_unl2.shape[0])]

            train_loss_cls, train_loss_dis, train_loss_gen, train_acc, test_acc = [0, 0, 0, 0, 0]
            # training
            for t in range(nr_batches_train):
                ran_from = t * FLAGS.batch_size
                ran_to = (t + 1) * FLAGS.batch_size
                # train discriminator
                feed_dict = {unl: trainx_unl[ran_from:ran_to],
                             is_training_pl: True}
                _, ld, sm = sess.run([train_dis_op, loss_dis, sum_op_dis], feed_dict=feed_dict)
                train_loss_dis += ld
                writer.add_summary(sm, batch)
                # train classifier
                feed_dict = {inp: trainx[ran_from:ran_to],
                             lbl: trainy[ran_from:ran_to],
                             is_training_pl: True}
                _, lc, acc, sm = sess.run([train_cls_op_ema, loss_cls, accuracy_cls, sum_op_cls], feed_dict=feed_dict)
                train_acc += acc
                train_loss_cls += lc
                writer.add_summary(sm, batch)
                # train generator
                feed_dict = {unl: trainx_unl2[ran_from:ran_to],
                             is_training_pl: True}
                _, lg, sm = sess.run([train_gen_op, loss_gen, sum_op_gen], feed_dict=feed_dict)
                train_loss_gen += lg
                writer.add_summary(sm, batch)
                # print
                if batch % FLAGS.freq_print == 0:
                    ran_from = np.random.randint(0,trainx_unl.shape[0]-FLAGS.batch_size)
                    ran_to = ran_from + FLAGS.batch_size
                    sm = sess.run(sum_op_im, feed_dict={unl:trainx_unl[ran_from:ran_to], is_training_pl: False})
                    writer.add_summary(sm, batch)
                    feed_dict={inp: trainx[ran_from:ran_to],
                                lbl: trainy[ran_from:ran_to],
                               unl: trainx_unl[ran_from:ran_to],
                                is_training_pl: True}
                    sess.run([print1,print2, print3, print4],feed_dict=feed_dict)
                batch += 1

            train_loss_gen /= nr_batches_train
            train_loss_cls /= nr_batches_train
            train_loss_dis /= nr_batches_train
            train_acc /= nr_batches_train

            # Testing
            sess.run(copy_graph)
            for t in range(nr_batches_test):
                ran_from = t * FLAGS.batch_size
                ran_to = (t + 1) * FLAGS.batch_size
                feed_dict = {inp: testx[ran_from:ran_to],
                             lbl: testy[ran_from:ran_to],
                             is_training_pl: False}
                test_acc += sess.run(accuracy_cls_test, feed_dict=feed_dict)
            test_acc /= nr_batches_test

            print("Epoch %d--Time = %ds | loss gen = %.4f | loss cls = %.4f | loss dis = %.4f "
                  "| train acc = %.4f| test acc = %.4f"
                  % (epoch, time.time() - begin, train_loss_gen, train_loss_cls, train_loss_dis, train_acc, test_acc))


if __name__ == '__main__':
    tf.app.run()