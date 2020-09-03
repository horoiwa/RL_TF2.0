import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import functools
import random
from pathlib import Path

import gym
from gym import wrappers
import numpy as np
from multiprocessing import Process, Pipe
import matplotlib.pyplot as plt

from env import SubProcVecEnv
from models import PolicyNetwork, ValueNetwork


def env_func():
    return gym.make("Pendulum-v0")


class PPOAgent:

    TRAJECTORY_SIZE = 64

    OBS_SPACE = 3

    ACTION_SPACE = 1

    GAMMA = 0.99

    LAMBDA = 0.95

    VALUE_COEF = 0.5

    ENTROPY_COEF = 0.01

    def __init__(self, n_envs):

        self.n_envs = n_envs

        self.policy = PolicyNetwork(action_space=self.ACTION_SPACE)

        self.value_network = ValueNetwork()

        self.vecenv = SubProcVecEnv([env_func for i in range(self.n_envs)])

        self.states = self.vecenv.reset()

        self.hiscore = 0

    def run(self, n_epochs):

        history = {"steps": [0], "scores": [0]}

        for n in range(1, n_epochs+1):

            print("EPOCH:", n)

            trajectory = self.run_nsteps(trajectory_size=self.TRAJECTORY_SIZE)

            self.update(trajectory)

            test_score = np.array(self.play(5)).mean()

            history["steps"].append(n*self.TRAJECTORY_SIZE*self.n_envs)

            history["scores"].append(test_score)

            print("Test score:", test_score)

            if n > 10 and test_score > self.hiscore:
                self.hiscore = test_score
                self.save_model()
                print("Hi Score Update:", self.hiscore)

        return history

    def run_nsteps(self, trajectory_size):

        trajectories = [{"s": np.zeros((self.TRAJECTORY_SIZE, self.OBS_SPACE), dtype=np.float32),
                         "a": np.zeros((self.TRAJECTORY_SIZE, self.ACTION_SPACE), dtype=np.float32),
                         "r": np.zeros((self.TRAJECTORY_SIZE, 1), dtype=np.float32),
                         "s2": np.zeros((self.TRAJECTORY_SIZE, self.OBS_SPACE), dtype=np.float32),
                         "done": np.zeros((self.TRAJECTORY_SIZE, 1), dtype=np.float32)}
                         for _ in range(self.n_envs)]

        for step in range(trajectory_size):

            states = np.array(self.states)

            actions = self.policy.sample_action(states)

            rewards, next_states, dones, info = self.vecenv.step(actions)

            for i in range(self.n_envs):
                trajectories[i]["s"][step] = states[i]
                trajectories[i]["a"][step] = actions[i]
                trajectories[i]["r"][step] = rewards[i]
                trajectories[i]["s2"][step] = next_states[i]
                trajectories[i]["done"][step] = dones[i]

            self.states = next_states

        for trajectory in trajectories:
            self.compute_advantage(trajectory)
            import sys
            sys.exit()

    def update(self, trajectory):

        mb_states, mb_actions, mb_target_values, mb_advantages = trajectory

    def save_model(self):

        self.ACNet.save_weights("checkpoints/best")

    def load_model(self, weights_path):

        self.ACNet.load_weights(weights_path)

    def play(self, n=1, monitordir=None):

        if monitordir:
            env = wrappers.Monitor(gym.make("CartPole-v1"),
                                   monitordir, force=True,
                                   video_callable=(lambda ep: True))
        else:
            env = gym.make("CartPole-v1")

        total_rewards = []

        for _ in range(n):
            obs = env.reset()

            done = False

            total_reward = 0

            while not done:

                action = self.ACNet.sample_action(obs)

                obs, reward, done, info = env.step(action[0])

                total_reward += reward

            total_rewards.append(total_reward)

        return total_rewards


def main():

    MONITOR_DIR = Path(__file__).parent / "log"

    agent = PPOAgent(n_envs=5)

    history = agent.run(n_epochs=10)

    #agent.load_model("checkpoints/best")
    #agent.play(5, monitordir=MONITOR_DIR)

    plt.plot(history["steps"], history["scores"])
    plt.xlabel("steps")
    plt.ylabel("Total rewards")
    plt.savefig(MONITOR_DIR / "testplay.png")


if __name__ == "__main__":
    main()
