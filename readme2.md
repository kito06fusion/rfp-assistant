We are changing things up to create a more interactive rfp assistant.

Frontend:

- For frontend we now use html. I personally like react frontend more. So change the frontend to use react.
- For the page layout a couple things need to be looked at. The output outputs a lot of blank pages within requirements.

Backend:

- The goal is to create a more interactive application. We now have the following sequence: OCR -> extraction -> Scope -> requirements -> Build Query -. Response. A rfp/tender can have a structure requirement. Meaning that our structure of creating a response per requirement is invalid. There should be a 2 way option, if a response structure is found in rfp, it should skip the phase of creating a response per requirement, and create a response following the required structure. If a response structure is not found in rfp, it should keep the response per requirement phase.
- Now the llm answers the requirements based on no knowledge, it guesses what our company can do. The idea is to create a interactive chatbot, in which the llm ask's the user for each unknown, what the answer is. For example: A requirements states that the response must include what platform is being used, the llm should ask the user in chat what the platform would be. So instead of the llm just creating each response based on guessing. For everything the llm does not know it asks. But if we hardcoded what platform our company uses, there is no need to ask.
