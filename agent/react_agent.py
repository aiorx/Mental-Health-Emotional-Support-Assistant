import sqlite3

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from agent.base_agent import BaseAgent

from model.factory import chat_model
from utils.prompt_loader import load_system_prompts
from agent.tools.agent_tools import (rag_summarize,get_weather,get_user_location,
                                     get_user_id,fetch_external_data,fill_context_for_report,get_current_month)
from agent.tools.middleware import monitor_tool,log_before_model,report_prompt_switch

# checkpoint = SqliteSaver(sqlite3.connect("D:/Mental Health Emotional Support Assistant/data/external/checkpoint.db",check_same_thread=False))
# checkpoint.setup()

class ReactAgent(BaseAgent):
    def __init__(self,):
        # self.checkpoint = SqliteSaver(sqlite3.connect("D:/Mental Health Emotional Support Assistant/data/external/checkpoint.db",check_same_thread=False))
        self.checkpoint = SqliteSaver(sqlite3.connect("/app/data/external/checkpoint.db", check_same_thread=False))
        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompts(),
            tools=[rag_summarize,fill_context_for_report,get_user_id,get_user_location,
                   get_weather,fill_context_for_report,fetch_external_data,get_current_month],
            middleware=[monitor_tool,log_before_model,report_prompt_switch],
            checkpointer=self.checkpoint,
        )
    def execute_stream(self, query: str, config=None):
        self.checkpoint.setup()
        input_dict = {
            "messages":[
                # {"role": "user", "content": query},
                HumanMessage(content=query)
            ]
        }

        for chunk in self.agent.stream(input_dict,config=config,stream_mode="values",context={"report": False}):
            latest_message = chunk["messages"][-1]
            if latest_message.content:
                yield latest_message.content.strip() + "\n"

    def chat(self,message: str) -> str:
        result = self.agent.invoke(
            {
                "message":[
                ("user", message)
                ]
            }
        )
        return result