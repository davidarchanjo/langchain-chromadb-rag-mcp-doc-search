import asyncio
from config import EnvironmentConfiguration
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient

config = EnvironmentConfiguration()  # type: ignore

async def run_agent():
    print(f"📡 Connecting to the MCP Server [{config.MCP_SERVER_NAME}] at [{config.MCP_SERVER_URL}]...")
    client = MultiServerMCPClient(connections = {
        config.MCP_SERVER_NAME: { "transport": "http", "url": config.MCP_SERVER_URL } # type: ignore
    })

    try:
        print("📥 Fetching and registering MCP tools...")
        discovered_tools = await client.get_tools()
        print(f"✅ Successfully registered {len(discovered_tools)} tools:")        
        tool_map = {tool.name: tool for tool in discovered_tools}
        for name in tool_map.keys():
            print(f"   ➡️ [Discovered] Name: '{name}'")

        llm = init_chat_model(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            model=config.LLM_MODEL_NAME,
            model_provider=config.LLM_MODEL_PROVIDER,
            temperature=config.LLM_TEMPERATURE
        )

        system_prompt = """
        You are a document retrieval assistant.

        Whenever the user asks a question whose answer may exist in the document store:

        1. Call the document search tool.
        2. Examine the retrieved documents.
        3. Answer exclusively from the retrieved content.
        4. If no relevant documents are found, reply:
          "I couldn't find that information in your documents."

        Never skip the search step.
        Never answer using your own knowledge when the answer should come from the document store.
        Do not fabricate information.
        Keep responses concise and factual.
        """      

        agent_executor = create_agent(model=llm, tools=discovered_tools, system_prompt=system_prompt)

        session_state = {"messages": []}
        print("-" * 50)

        while True:
            user_prompt = await asyncio.to_thread(input, "\n👨 User Query ('quit' to exit): ")

            if user_prompt.strip().lower() == "quit":
                print("\n👋 Terminating session. Goodbye!")
                break

            if not user_prompt.strip():
                continue

            session_state["messages"].append(("user", user_prompt))
            
            result = await agent_executor.ainvoke(session_state)  # type: ignore

            session_state["messages"] = result["messages"]

            print(f"\n🤖 Agent Answer: {session_state['messages'][-1].content}")
            print("-" * 50)

    except Exception as e:
        print(f"❌ Error encountered during client execution: {e}")

if __name__ == "__main__":
    asyncio.run(run_agent())