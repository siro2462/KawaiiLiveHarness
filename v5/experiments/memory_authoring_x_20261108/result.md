Public X research is now part of the fictional-memory authoring workflow. The existing [authoring recipe](../v_memory_structure_20261103/recipe.md) covers source selection, age and time verification, concrete observations, subsequent actions, independent fictional specifications, provenance and fragment validation.

On 2026-11-07, twscrape 0.21.0 retrieved five posts for a connectivity check and ten posts for an age-keyword search. These fifteen returned posts establish that the retrieval path worked. The search included references to other people's ages and other keyword matches, so the number of suitable first-person accounts from the requested age range remains unscored. twikit 2.3.3 is installed as a fallback; successful retrieval with it has not been demonstrated.

The local reusable skill now routes fictional-memory requests to this recipe. Its environment-specific reference records the working Python environment, the reader command and the authorized local HAR input. The local reader accepts both the previous cookie JSON formats and a supplied HAR, uses a complete authentication pair from an X request, and records retrieval time. Authentication values and source prose remain in local storage.

The author uses public posts to find a person's purpose, the detail they noticed, their interpretation at that time and the action that followed. Real place and product names are checked where they affect the scene. The fictional specification records which details were authored, then is saved and hashed before fragments are constructed. Source matching, authoring quality and later speech quality have distinct review states.

The new authoring workflow has not been evaluated in a matched speech experiment. The latest three manually authored candidates predate the direct X retrieval. Existing completed speech reviews retain their recorded limitations, including unsupported additions and repetition.

Eighteen local checks passed for cookie-format compatibility, X-domain filtering, complete request pairs, sanitized-HAR rejection, the provided HAR and the saved retrieval receipts. The updated skill passed its structural validator.
