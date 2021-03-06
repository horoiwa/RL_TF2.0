from pathlib import Path
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
from dataclasses import dataclass
import random
import collections
from datetime import datetime

import numpy as np
import pandas as pd
import tensorflow as tf
from PIL import Image
import tensorflow.keras.layers as kl
import matplotlib.pyplot as plt
import gym
from gym import wrappers

from models import QNetwork
from buffer import PrioritizedReplayBuffer


@dataclass
class Experience:

    state: np.ndarray

    action: int

    reward: float

    next_state: np.ndarray

    done: bool


def preprocess(frame):

    frame = Image.fromarray(frame)
    frame = frame.convert("L")

    # スコア表示を消せるがUFOを打てなくなる
    frame = frame.crop((0, 20, 160, 200))

    # スコア表示あるがUFOを打てる
    #frame = frame.crop((0, 0, 160, 200))

    frame = frame.resize((84, 84))
    frame = np.array(frame, dtype=np.float32)
    frame = frame / 255

    return frame


class DQNAgent:

    MAX_EXPERIENCES = 350000

    MIN_EXPERIENCES = 30000

    ENV_ID = "SpaceInvadersDeterministic-v4"

    ACTION_SPACE = 4

    NUM_FRAMES = 4

    BATCH_SIZE = 32

    UPDATE_PERIOD = 4

    COPY_PERIOD = 10000

    INPUT_SHAPE = (None, 84, 84, 4)

    BETA_INIT = 0.4

    def __init__(self, gamma=0.98):
        """
            gammma: 割引率
            epsilon: 探索と活用の割合
        """

        self.env = gym.make(self.ENV_ID)

        self.gamma = gamma

        self.epsion = 1.0

        self.global_steps = 0

        self.q_network = QNetwork(self.ACTION_SPACE)

        self.q_network.build(input_shape=self.INPUT_SHAPE)

        self.target_network = QNetwork(self.ACTION_SPACE)

        self.target_network.build(input_shape=self.INPUT_SHAPE)

        self.replay_buffer = PrioritizedReplayBuffer(
            max_experiences=self.MAX_EXPERIENCES)

        self.hiscore = 0

    def play(self, n_episodes):

        total_rewards = []

        recent_scores = collections.deque(maxlen=5)

        for n in range(n_episodes):

            self.beta = self.BETA_INIT + (1-self.BETA_INIT) * (n / n_episodes)

            self.epsilon = 1.0 - min(0.95, self.global_steps * 0.95 / 500000)

            total_reward, localsteps = self.play_episode()

            total_rewards.append(total_reward)

            recent_scores.append(total_reward)

            recent_average_score = sum(recent_scores) / len(recent_scores)

            print(f"Episode {n}: {total_reward}")
            print(f"Local steps {localsteps}")
            print(f"Experiences {len(self.replay_buffer)}")
            print(f"Current epsilon {self.epsilon}")
            print(f"Current beta {self.beta}")
            print(f"Current maxp {self.replay_buffer.max_priority}")
            print(f"Global step {self.global_steps}")
            print(f"recent average score {recent_average_score}")
            print()

            if recent_average_score > self.hiscore:
                self.hiscore = recent_average_score
                print(f"HISCORE Updated: {self.hiscore}")
                self.save_model()

        return total_rewards

    def play_episode(self):

        total_reward = 0

        steps = 0

        done = False

        frames = collections.deque(maxlen=self.NUM_FRAMES)

        frame = self.env.reset()
        for _ in range(self.NUM_FRAMES):
            frames.append(preprocess(frame))

        for _ in range(random.randint(45, 55)):
            frame, reward, done, info = self.env.step(1)
            frames.append(preprocess(frame))

        lives = info["ale.lives"]

        state = np.stack(frames, axis=2)[np.newaxis, ...]

        while not done:

            action = self.sample_action(state)

            frame, reward, done, info = self.env.step(action)

            #: reward clipping
            reward = 1 if reward else 0

            frames.append(preprocess(frame))

            next_state = np.stack(frames, axis=2)[np.newaxis, ...]

            if info["ale.lives"] != lives:
                lives = info["ale.lives"]
                exp = Experience(state, action, reward, next_state, True)
            else:
                exp = Experience(state, action, reward, next_state, done)

            self.replay_buffer.add_experience(exp)

            state = next_state

            total_reward += reward

            steps += 1

            self.global_steps += 1

            if self.global_steps % self.UPDATE_PERIOD == 0:
                self.update_qnetwork()

            if self.global_steps % self.COPY_PERIOD == 0:
                print("==Update target newwork==")
                self.target_network.set_weights(self.q_network.get_weights())

        return total_reward, steps

    def sample_action(self, state, epsilon=None):
        """探索と活用"""

        epsilon = epsilon if epsilon else self.epsilon

        if np.random.random() < epsilon:
            random_action = np.random.choice(self.env.action_space.n)
            return random_action
        else:
            selected_action = np.argmax(self.q_network.predict(state))
            return selected_action

    def update_qnetwork(self):
        """ Q-Networkの訓練
            ただしExperiencesが規定数に達していないうちは何もしない
        """
        if len(self.replay_buffer) < self.MIN_EXPERIENCES:
            return

        indices, weights, experiences = self.replay_buffer.get_minibatch(self.BATCH_SIZE, self.beta)

        states = [exp.state for exp in experiences]

        actions = [exp.action for exp in experiences]

        rewards = [exp.reward for exp in experiences]

        next_states = [exp.next_state for exp in experiences]

        dones = [exp.done for exp in experiences]

        #: Nature DQN
        #maxQ_actions = np.argmax(self.target_network(np.vstack(next_states)), axis=1)

        #: Double DQN
        maxQ_actions = np.argmax(self.q_network(np.vstack(next_states)), axis=1)

        maxQ_actions_onehot = np.identity(self.ACTION_SPACE)[maxQ_actions]

        next_Qs = self.target_network(np.vstack(next_states))

        next_maxQs = np.max(next_Qs * maxQ_actions_onehot, axis=1)

        target_values = [reward + self.gamma * next_q if not done else reward
                         for reward, next_q, done
                         in zip(rewards, next_maxQs, dones)]

        td_errors = self.q_network.update(np.vstack(states), np.array(actions),
                                          np.array(target_values), weights)

        self.replay_buffer.update_priority(indices, td_errors)

    def save_model(self):

        self.q_network.save_weights("checkpoints/best")

    def load_model(self, weights_path):

        self.q_network.load_weights(weights_path)

        self.target_network.load_weights(weights_path)

    def testplay(self, n=1, monitordir=None):

        if monitordir:
            env = wrappers.Monitor(gym.make(self.ENV_ID),
                                   monitordir, force=True,
                                   video_callable=(lambda ep: ep % 1 == 0))
        else:
            env = gym.make(self.ENV_ID)

        total_rewards = []

        for i in range(n):

            print(f"Start {i}")

            frames = collections.deque(maxlen=4)

            frame = preprocess(env.reset())

            for _ in range(self.NUM_FRAMES):
                frames.append(frame)

            for _ in range(np.random.randint(45, 55)):

                frame, _, _, _ = env.step(1)

                frames.append(preprocess(frame))

            done = False

            total_reward = 0

            while not done:

                state = np.stack(frames, axis=2)[np.newaxis, ...]

                action = self.sample_action(state, epsilon=0.05)

                frame, reward, done, _ = env.step(action)

                frames.append(preprocess(frame))

                total_reward += reward

            total_rewards.append(total_reward)

            print(i, total_reward)

        return total_rewards


def main():

    TOTAL_EPISODES = 7000

    start = datetime.now()

    monitor_dir = Path(__file__).parent / "history"

    agent = DQNAgent()
    history = agent.play(n_episodes=TOTAL_EPISODES)

    plt.plot(range(len(history)), history)
    plt.xlabel("episodes")
    plt.ylabel("Total Reward")
    plt.savefig(monitor_dir / "dqn_breakout-det-v4.png")

    df = pd.DataFrame()
    df["Total Reward"] = history
    df.to_csv(monitor_dir / "dqn_breakout-det-v4.csv", index=None)

    end = datetime.now() - start

    print(end)


def play_only(n):

    monitor_dir = Path(__file__).parent / "history"

    agent = DQNAgent()

    agent.load_model("checkpoints/best")

    total_rewards = agent.testplay(n=n, monitordir=monitor_dir)

    print(total_rewards)


if __name__ == "__main__":

    main()

    play_only(n=10)
