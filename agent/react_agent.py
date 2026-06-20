from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from model.factory import chat_model
from utils.prompt_loader import load_system_prompts
from agent.tools.agent_tools import (rag_summarize,get_weather,get_user_location,
                                     get_user_id,fetch_external_data,fill_context_for_report,get_current_month)
from agent.tools.middleware import monitor_tool,log_before_model,report_prompt_switch

class ReactAgent():
    def __init__(self):
        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompts(),
            tools=[rag_summarize,fill_context_for_report,get_user_id,get_user_location,
                   get_weather,fill_context_for_report,fetch_external_data,get_current_month],
            middleware=[monitor_tool,log_before_model,report_prompt_switch]
        )
    def execute_stream(self, query: str):
        input_dict = {
            "messages":[
                # {"role": "user", "content": query},
                HumanMessage(content=query)
            ]
        }

        for chunk in self.agent.stream(input_dict,stream_mode="values",context={"report": False}):
            latest_message = chunk["messages"][-1]
            if latest_message.content:
                yield latest_message.content.strip() + "\n"