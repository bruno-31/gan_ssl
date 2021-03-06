import os
import time

import numpy as np
import tensorflow as tf
import sys
sys.path.insert(0, "/home/data/bruno/ssl/data")
from data import svhn_data
import svhn_chi_gan

# os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

flags = tf.app.flags
flags.DEFINE_integer("batch_size", 100, "batch size [128]")
flags.DEFINE_string('data_dir', './data', 'data directory')
flags.DEFINE_string('logdir', './log_svhn/000', 'log directory')
flags.DEFINE_integer('seed', 4, 'seed ')
flags.DEFINE_integer('seed_data', 4, 'seed data')
flags.DEFINE_integer('labeled', 100, 'labeled data per class')
flags.DEFINE_float('learning_rate', 0.0003, 'learning_rate[0.003]')
flags.DEFINE_integer('freq_print', 200, 'frequency image print tensorboard [20]')
flags.DEFINE_float('unl_weight', 1.0, 'unlabeled weight [1.]')
flags.DEFINE_float('lbl_weight', 1.0, 'unlabeled weight [1.]')
flags.DEFINE_float('gen_weight_fmatch', 1.0, 'unlabeled weight [1.]')
flags.DEFINE_float('gen_weight_bin', 0.0 , 'unlabeled weight [1.]')
flags.DEFINE_float('ma_decay', 0.998 , 'moving average testing, 0 to disable  [0.9999]')
flags.DEFINE_integer('freq_save', 100, 'frequency saver epoch')


FLAGS = flags.FLAGS
FLAGS._parse_flags()
print("\nParameters:")
for attr, value in sorted(FLAGS.__flags.items()):
    print("{}={}".format(attr.lower(), value))
print("")


def display_progression_epoch(j, id_max):
    batch_progression = int((j / id_max) * 100)
    sys.stdout.write(str(batch_progression) + ' % epoch' + chr(13))
    _ = sys.stdout.flush

def get_getter(ema):
    def  ema_getter(getter, name, *args, **kwargs):
        var = getter(name, *args,**kwargs)
        ema_var = ema.average(var)
        return ema_var if ema_var else var
    return ema_getter

def main(_):
    if not os.path.exists(FLAGS.logdir):
        os.mkdir(FLAGS.logdir)

    # Random seed
    rng = np.random.RandomState(FLAGS.seed)  # seed labels
    rng_data = np.random.RandomState(FLAGS.seed_data)  # seed shuffling

    def rescale(mat):
        return np.transpose(( (-127.5 + mat) / 127.5), (3, 0, 1, 2))

    trainx, trainy = svhn_data.load(FLAGS.data_dir, 'train')
    testx, testy = svhn_data.load(FLAGS.data_dir, 'test')
    # testx, testy =svhn_data.load(FLAGS.data_dir, 'train')
    trainx = rescale(trainx)
    testx = rescale(testx)
    trainx_unl = trainx.copy()
    trainx_unl2 = trainx.copy()
    nr_batches_train = int(trainx.shape[0] / FLAGS.batch_size)
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
    # for j in range(10):
    #     txs.append(trainx[trainy == j][:])
    #     tys.append(trainy[trainy == j][:])
    txs = np.concatenate(txs, axis=0)
    tys = np.concatenate(tys, axis=0)

    print("Data:")
    print('train shape %d | batch training %d \ntest shape %d  |  batch  testing %d' \
            %(trainx.shape[0], nr_batches_train, testx.shape[0],nr_batches_test))
    print('histogram train',np.histogram(trainy,bins=10)[0])
    print('histogram test ', np.histogram(testy, bins=10)[0])
    print("histogram labeled",np.histogram(tys, bins=10)[0])
    print("")

    '''construct graph'''
    print('constructing graph')
    unl = tf.placeholder(tf.float32, [FLAGS.batch_size, 32, 32, 3], name='unlabeled_data_input_pl')
    is_training_pl = tf.placeholder(tf.bool, [], name='is_training_pl')
    inp = tf.placeholder(tf.float32, [FLAGS.batch_size, 32, 32, 3], name='labeled_data_input_pl')
    lbl = tf.placeholder(tf.int32, [FLAGS.batch_size], name='lbl_input_pl')
    lr_pl = tf.placeholder(tf.float32,[],name='learning_rate_pl')
    acc_train_pl = tf.placeholder(tf.float32, [], 'acc_train_pl')
    acc_test_pl = tf.placeholder(tf.float32, [], 'acc_test_pl')

    gen = svhn_chi_gan.generator
    dis = svhn_chi_gan.discriminator

    ema = tf.train.ExponentialMovingAverage(decay=FLAGS.ma_decay)

    random_z = tf.random_uniform([FLAGS.batch_size, 128], name='random_z')
    with tf.variable_scope('generator_model') as scope:
        # gen(random_z,is_training_pl,init=True)
        # scope.reuse_variables()
        gen_inp = gen(random_z, is_training_pl)

    with tf.variable_scope('discriminator_model') as scope:
        # dis(inp, is_training_pl, init=True)
        # scope.reuse_variables()
        l_lab_cls, l_lab_dis, _,_,_= dis(inp, is_training_pl)
        scope.reuse_variables()

        l_gen_cls, l_gen_dis, layer_fake, lf2,lf3 = dis(gen_inp, is_training_pl)
        l_unl_cls, l_unl_dis, layer_real, lr2,lr3 = dis(unl, is_training_pl)
        # l_test, _, _, _, _ = dis(inp, is_training_pl, getter=get_getter(ema))


    # with tf.variable_scope("model_test"):
    #     l_test, _,_,_,_ = dis(inp, is_training_pl)

    with tf.name_scope('loss_functions'):
        xentropy = tf.nn.sparse_softmax_cross_entropy_with_logits
        sigmoid = tf.nn.sigmoid_cross_entropy_with_logits
        loss_cls = tf.reduce_mean(xentropy(logits=l_lab_cls, labels=lbl))
        loss_dis_unl = tf.reduce_mean(sigmoid(logits=l_unl_dis, labels=tf.ones_like(l_unl_dis)))
        loss_dis_gen = tf.reduce_mean(sigmoid(logits=l_gen_dis, labels=tf.zeros_like(l_gen_dis)))
        loss_dis = loss_dis_unl + loss_dis_gen


        # loss_lab = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(logits=l_lab_cls,labels=lbl))
        # l_unl = tf.reduce_logsumexp(l_unl_cls, axis=1)
        # l_gen = tf.reduce_logsumexp(l_gen_cls, axis=1)
        # loss_unl = - 0.5 * tf.reduce_mean(l_unl) \
        #            + 0.5 * tf.reduce_mean(tf.nn.softplus(l_unl)) \
        #            + 0.5 * tf.reduce_mean(tf.nn.softplus(l_gen))
        # loss_dis = FLAGS.unl_weight * loss_unl + FLAGS.lbl_weight * loss_lab


        accuracy_dis_gen = tf.reduce_mean(tf.cast(tf.less(l_gen_dis, 0), tf.float32))
        accuracy_dis_unl = tf.reduce_mean(tf.cast(tf.greater(l_unl_dis, 0), tf.float32))

        correct_pred = tf.equal(tf.cast(tf.argmax(l_lab_cls, 1), tf.int32), tf.cast(lbl, tf.int32))
        accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))


        # GENERATOR
        m1 = tf.reduce_mean(layer_real, axis=0)
        m2 = tf.reduce_mean(layer_fake, axis=0)
        m11 = tf.reduce_mean(lr2, axis=0)
        m22 = tf.reduce_mean(lf2, axis=0)
        m111 = tf.reduce_mean(lr3, axis=0)
        m222 = tf.reduce_mean(lf3, axis=0)
        # loss_gen_fmatch = tf.reduce_mean(tf.square(m1 - m2)) + tf.reduce_mean(tf.square(m11 - m22))+ tf.reduce_mean(tf.square(m111 - m222))
        loss_gen_fmatch = tf.reduce_mean(tf.square(m1 - m2))

        loss_gen_bin = tf.reduce_mean(sigmoid(logits=l_gen_dis, labels=tf.ones_like(l_gen_dis)))
        fool_rate = tf.reduce_mean(tf.cast(tf.greater(l_gen_dis, 0), tf.float32))
        loss_gen = FLAGS.gen_weight_bin * loss_gen_bin + FLAGS.gen_weight_fmatch * loss_gen_fmatch

        grad = tf.gradients(l_gen_cls, random_z)
        dd = tf.sqrt(tf.reduce_sum(tf.square(grad),axis=1))
        ddx = 0.01* tf.reduce_mean(tf.square(dd-0))

        # loss_cls += ddx
        # print(ddx)


    with tf.name_scope('optimizers'):
        # control op dependencies for batch norm and trainable variables
        tvars = tf.trainable_variables()
        dvars = [var for var in tvars if 'discriminator_model' in var.name]
        disvars = [var for var in tvars if 'discriminator_model/dis_weight' in var.name]
        clsvars = [var for var in tvars if 'discriminator_model/cls_weight' in var.name]
        sharedvars = [var for var in tvars if 'discriminator_model/shared_weights' in var.name]
        gvars = [var for var in tvars if 'generator_model' in var.name]
        testvars = [var for var in tvars if 'model_test' in var.name]

        update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        update_ops_gen = [x for x in update_ops if ('generator_model' in x.name)]
        update_ops_dis = [x for x in update_ops if ('discriminator_model' in x.name)]


        optimizer_dis = tf.train.AdamOptimizer(learning_rate=lr_pl, beta1=0.5, name='dis_optimizer')
        optimizer_gen = tf.train.AdamOptimizer(learning_rate=lr_pl, beta1=0.5, name='gen_optimizer')
        optimizer_cls = tf.train.AdamOptimizer(learning_rate=lr_pl, beta1=0.5, name='cls_optimizer')

        with tf.control_dependencies(update_ops_gen):
            train_gen_op = optimizer_gen.minimize(loss_gen, var_list=gvars)

        dis_op = optimizer_dis.minimize(loss_dis, var_list=disvars+sharedvars)
        cls_op = optimizer_cls.minimize(loss_cls, var_list=clsvars+sharedvars)

        # ema = tf.train.ExponentialMovingAverage(decay=FLAGS.ma_decay)
        maintain_averages_op = tf.group(ema.apply(dvars))

        # with tf.variable_scope("model_test"):
        # l_test, _, _, _, _ = dis(inp, is_training_pl, getter=get_getter(ema))

        # correct_pred_test = tf.equal(tf.cast(tf.argmax(l_test, 1), tf.int32), tf.cast(lbl, tf.int32))
        # accuracy_test = tf.reduce_mean(tf.cast(correct_pred_test, tf.float32))

        # with tf.control_dependencies(update_ops_dis):
        with tf.control_dependencies([dis_op]):
            train_dis_op = maintain_averages_op

        # with tf.control_dependencies(update_ops_dis): #batchnorm
        with tf.control_dependencies([cls_op]):
            train_cls_op = maintain_averages_op

        # with tf.control_dependencies(update_ops_dis):  # batchnorm
        #     with tf.control_dependencies([maintain_averages_op]):
        #         train_cls_op = cls_op

        # with tf.control_dependencies(update_ops_dis):
        #     with tf.control_dependencies([train_dis_op]):
        #         dis_op = tf.group(maintain_averages_op)
        # ema.average(y)

        # copy_graph = [tf.assign(x, ema.average(y)) for x, y in zip(testvars, dvars)]
        # [print(var.name) for var in clsvars]
        # print('')
        # [print(var.name) for var in sharedvars]

    with tf.name_scope('summary'):
        with tf.name_scope('dis_summary'):
            tf.summary.scalar('discriminator_accuracy_unl', accuracy_dis_unl, ['dis'])
            tf.summary.scalar('discriminator_accuracy_gen', accuracy_dis_gen, ['dis'])
            tf.summary.scalar('loss_discriminator', loss_dis, ['dis'])

        with tf.name_scope('cls_summary'):
            # tf.summary.scalar('loss_cls', loss_cls, ['cls'])
            tf.summary.scalar('classifier_accuracy', accuracy, ['cls'])

        with tf.name_scope('gen_summary'):
            tf.summary.scalar('loss_generator', loss_gen, ['gen'])
            tf.summary.scalar('fool_rate', fool_rate, ['gen'])

        with tf.name_scope('image_summary'):
            tf.summary.image('gen_digits', gen_inp, 5, ['image'])
            tf.summary.image('input_images', unl, 5, ['image'])

        with tf.name_scope('epoch_summary'):
            tf.summary.scalar('accuracy_train', acc_train_pl, ['epoch'])
            tf.summary.scalar('accuracy_test', acc_test_pl, ['epoch'])
            tf.summary.scalar('learning_rate', lr_pl,['epoch'])

        sum_op_dis = tf.summary.merge_all('dis')
        sum_op_gen = tf.summary.merge_all('gen')
        sum_op_cls = tf.summary.merge_all('cls')
        sum_op_im = tf.summary.merge_all('image')
        sum_op_epoch = tf.summary.merge_all('epoch')

    # [print(var.name) for var in tf.trainable_variables()]

    saver = tf.train.Saver()

    '''//////perform training //////'''
    print('start training')
    with tf.Session() as sess:
        init_gen = [var.initializer for var in gvars][:-3]
        sess.run(init_gen)
        init = tf.global_variables_initializer()
        sess.run(init, feed_dict={inp:trainx_unl[:FLAGS.batch_size],unl: trainx_unl[:FLAGS.batch_size], is_training_pl: True})
        print('data driven initialization done')
        writer = tf.summary.FileWriter(FLAGS.logdir, sess.graph)
        train_batch = 0

        for epoch in range(1200):
            begin = time.time()
            train_loss_lab, train_loss_unl, train_loss_gen, train_acc, test_acc = [0, 0, 0, 0, 0]

            lr = FLAGS.learning_rate * min(3-epoch/400,1)

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

            # training
            for t in range(nr_batches_train):

                display_progression_epoch(t, nr_batches_train)
                ran_from = t * FLAGS.batch_size
                ran_to = (t + 1) * FLAGS.batch_size

                # # train discriminator
                # feed_dict = {unl: trainx_unl[ran_from:ran_to],
                #              inp: trainx[ran_from:ran_to],
                #              lbl: trainy[ran_from:ran_to],
                #              is_training_pl: True, lr_pl: lr}
                # _, lu, sm = sess.run([train_dis_op, loss_dis, sum_op_dis],
                #                      feed_dict=feed_dict)
                # train_loss_unl += lu
                # writer.add_summary(sm, train_batch)

                # train classifier
                feed_dict = {is_training_pl: True,
                             unl: trainx_unl[ran_from:ran_to],
                             inp: trainx[ran_from:ran_to],
                             lbl: trainy[ran_from:ran_to],
                             lr_pl: lr}
                _, acc, lb, sm = sess.run([train_cls_op, accuracy, loss_cls, sum_op_cls],
                                              feed_dict=feed_dict)
                train_loss_lab += lb
                train_acc += acc
                writer.add_summary(sm, train_batch)

                # train generator
                # _, lg, sm = sess.run([train_gen_op, loss_gen, sum_op_gen], feed_dict={unl: trainx_unl2[ran_from:ran_to],
                #                                                                       is_training_pl: True,
                #                                                                       lr_pl:lr})
                # train_loss_gen += lg
                # train_batch += 1
                # writer.add_summary(sm, train_batch)

                if t % FLAGS.freq_print == 0:
                    ran_from = np.random.randint(0, trainx_unl.shape[0] - FLAGS.batch_size)
                    ran_to = ran_from + FLAGS.batch_size
                    sm = sess.run(sum_op_im, feed_dict={unl: trainx_unl[ran_from:ran_to],
                                                        is_training_pl: False})
                    writer.add_summary(sm, train_batch)

            train_loss_lab /= nr_batches_train
            train_loss_unl /= nr_batches_train
            train_loss_gen /= nr_batches_train
            train_acc /= nr_batches_train

            # Testing
            # sess.run(copy_graph)
            for t in range(nr_batches_test):
                ran_from = t * FLAGS.batch_size
                ran_to = (t + 1) * FLAGS.batch_size
                feed_dict = {inp: testx[ran_from:ran_to],
                             lbl: testy[ran_from:ran_to],
                             is_training_pl: False}
                test_acc += sess.run(accuracy, feed_dict=feed_dict)

            test_acc /= nr_batches_test

            #tensorboard epoch
            sum = sess.run(sum_op_epoch, feed_dict={acc_train_pl: train_acc,acc_test_pl: test_acc,lr_pl: lr})
            writer.add_summary(sum, epoch)

            # saving
            if epoch % FLAGS.freq_save == 0:
                save_path = saver.save(sess, os.path.join(FLAGS.logdir, 'model.ckpt'))
                print("Model saved in file: %s" % (save_path))

            print("epoch %d time = %ds lr = %0.2e | loss gen = %.4f | loss lab = %.4f | loss unl = %.4f "
                  "| train acc = %.4f| test acc = %.4f"
                  % (epoch, time.time() -begin,lr, train_loss_gen, train_loss_lab, train_loss_unl, train_acc, test_acc))



if __name__ == '__main__':
    tf.app.run()
