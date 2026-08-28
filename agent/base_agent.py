from abc import ABC, abstractmethod

class BaseAgent(ABC):
    @abstractmethod
    def chat(self, message :str) -> str:
        """
                统一聊天接口

                Parameters
                ----------
                message : str
                    用户输入

                Returns
                -------
                str
                    Agent 回复
        """
        pass
