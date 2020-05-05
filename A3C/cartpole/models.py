import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import tensorflow as tf
import tensorflow.keras.layers as kl
import tensorflow_probability as tfp
import numpy as np


class SharedNetwork(tf.keras.Model):

    def __init__(self):

        super(SharedNetwork, self).__init__()

        self.dense1 = kl.Dense(32, activation="relu", name="dense1",
                               kernel_initializer="he_normal")

        self.dense2 = kl.Dense(32, activation="relu", name="dense2",
                               kernel_initializer="he_normal")

    def call(self, x):

        x = self.dense1(x)
        x = self.dense2(x)

        return x


class ValueNetwork(tf.keras.Model):

    def __init__(self, shared_network):

        super(ValueNetwork, self).__init__()

        self.shared_network = shared_network

        self.out = kl.Dense(1, name="out",
                            kernel_initializer="he_normal")

        self.optimizer = tf.keras.optimizers.Adam(lr=0.001)

    @tf.function
    def call(self, x):
        x = self.shared_network(x)
        out = self.out(x)
        return out

    def predict(self, state):
        state = np.atleast_2d(state)
        return self(state).numpy()[0][0]

    def compute_grads(self, states, discounted_rewards):
        """
           loss =  MSE(discouted_rewards - V(state)) = MSE(Advantages)
        """

        with tf.GradientTape() as tape:

            estimated_values = self(states)

            loss = tf.reduce_mean(
                tf.square(discounted_rewards - estimated_values))

        variables = self.trainable_variables
        gradients = tape.gradient(loss, variables)

        return gradients


class PolicyNetwork(tf.keras.Model):

    ALPHA = 0.005

    def __init__(self, shared_network, action_space):

        super(PolicyNetwork, self).__init__()

        self.action_space = action_space

        self.shared_network = shared_network

        self.dense1 = kl.Dense(action_space, name="out",
                               kernel_initializer="he_normal")

        self.softmax = kl.Softmax()

        self.optimizer = tf.keras.optimizers.Adam(lr=0.001)

    @tf.function
    def call(self, x):
        x = self.shared_network(x)
        logits = self.dense1(x)
        probs = self.softmax(logits)
        return probs

    def sample_action(self, state):
        state = np.atleast_2d(state).astype(np.float32)
        probs = self(state)
        cdist = tfp.distributions.Categorical(probs=probs)
        action = cdist.sample()
        return action.numpy()[0]

    def compute_grads(self,  states, actions, advantages):
        """
            Maximize: pi(a | s) * Advantage + alpha * entropy_of_pi(s)

            alpha: 正則化係数
        """
        actions_onehot = tf.one_hot(actions, self.action_space)
        with tf.GradientTape() as tape:
            action_probs = self(states)
            selected_action_probs = tf.reduce_max(
                action_probs * actions_onehot, axis=1)

            entropy = -tf.reduce_sum(
                action_probs * tf.math.log(action_probs + 1e-20), axis=1)

            loss = tf.reduce_mean(
                -1 * (selected_action_probs * advantages + self.ALPHA * entropy))

        variables = self.trainable_variables
        gradients = tape.gradient(loss, variables)

        return gradients



def create_networks(action_space):
    shared_network = SharedNetwork()
    value_network = ValueNetwork(shared_network=shared_network)
    policy_network = PolicyNetwork(shared_network=shared_network,
                                   action_space=action_space)
    return value_network, policy_network



if __name__ == "__main__":
    states = np.array([[-0.10430691, -1.55866031, 0.19466207, 2.51363456],
                       [-0.10430691, -1.55866031, 0.19466207, 2.51363456],
                       [-0.10430691, -1.55866031, 0.19466207, 2.51363456]])
    states.astype(np.float32)

    actions = [0, 1, 1]

    target_values = [1, 1, 1]

    shared_network = SharedNetwork()
    value_network = ValueNetwork(shared_network=shared_network)
    policy_network = PolicyNetwork(shared_network=shared_network,
                                   action_space=2)

    print(value_network(states))
    print(policy_network(states))

    print("")
    print("probs")
    state = np.array([-0.10430691, -1.55866031, 0.19466207, 2.51363456])
    print(policy_network.sample_action(state))
    print(value_network.predict(state))
